package llmadmin

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"encoding/base64"
	"encoding/hex"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/llm"
)

func credentialEnvelope(t *testing.T, keyMaterial, plaintext string) string {
	t.Helper()
	key, err := hex.DecodeString(keyMaterial)
	if err != nil {
		t.Fatal(err)
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		t.Fatal(err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		t.Fatal(err)
	}
	nonce := make([]byte, gcm.NonceSize())
	for index := range nonce {
		nonce[index] = byte(index + 1)
	}
	sealed := gcm.Seal(nil, nonce, []byte(plaintext), nil)
	ciphertext := sealed[:len(sealed)-gcm.Overhead()]
	tag := sealed[len(sealed)-gcm.Overhead():]
	return "aes-256-gcm:v1:" + base64.StdEncoding.EncodeToString(nonce) + ":" + base64.StdEncoding.EncodeToString(tag) + ":" + base64.StdEncoding.EncodeToString(ciphertext)
}

type healthResolverQueryer struct {
	rows        llm.SQLRows
	tenantID    string
	query       string
	args        []any
	plainCalled bool
}

func (q *healthResolverQueryer) QueryContext(context.Context, string, ...any) (llm.SQLRows, error) {
	q.plainCalled = true
	return nil, nil
}

func (q *healthResolverQueryer) QueryTenantContext(_ context.Context, tenantID, query string, args ...any) (llm.SQLRows, error) {
	q.tenantID = tenantID
	q.query = query
	q.args = append([]any(nil), args...)
	return q.rows, nil
}

type healthResolverRows struct {
	values [][]any
	index  int
}

func (r *healthResolverRows) Next() bool   { return r.index < len(r.values) }
func (r *healthResolverRows) Close() error { return nil }
func (r *healthResolverRows) Err() error   { return nil }
func (r *healthResolverRows) Scan(dest ...any) error {
	row := r.values[r.index]
	r.index++
	for index, value := range row {
		switch target := dest[index].(type) {
		case *string:
			*target = value.(string)
		case *bool:
			*target = value.(bool)
		}
	}
	return nil
}

func TestSQLHealthCredentialResolverFailsClosedWithoutEncryptionKey(t *testing.T) {
	_, err := NewSQLHealthCredentialResolver(SQLHealthCredentialResolverConfig{Queryer: &healthResolverQueryer{}})
	if ErrorCode(err) != "LLM_CREDENTIAL_ENCRYPTION_UNCONFIGURED" {
		t.Fatalf("missing encryption key was accepted: %v", err)
	}
}

func TestSQLHealthCredentialResolverUsesTenantRLSAndDecryptsOwnedEnabledTarget(t *testing.T) {
	keyMaterial := strings.Repeat("8", 64)
	envelope := credentialEnvelope(t, keyMaterial, "sk-health-production")
	queryer := &healthResolverQueryer{rows: &healthResolverRows{values: [][]any{{
		"channel-1", "model-1", "https://provider.example/v1", envelope, true, true, true,
	}}}}
	resolver, err := NewSQLHealthCredentialResolver(SQLHealthCredentialResolverConfig{
		Queryer: queryer, CredentialKeyMaterial: keyMaterial,
	})
	if err != nil {
		t.Fatalf("construct resolver: %v", err)
	}

	target, err := resolver.ResolveHealthTarget(context.Background(), "tenant-1", "project-1", "channel-1", "model-1")
	if err != nil {
		t.Fatalf("resolve health target: %v", err)
	}
	if queryer.plainCalled || queryer.tenantID != "tenant-1" {
		t.Fatalf("resolver bypassed tenant context: %#v", queryer)
	}
	for _, required := range []string{"JOIN projects", "c.enabled", "m.enabled", "c.tenant_id::text = $1", "p.project_id::text = $2", "c.channel_id::text = $3", "m.model_id = $4"} {
		if !strings.Contains(queryer.query, required) {
			t.Fatalf("resolver query lacks %q: %s", required, queryer.query)
		}
	}
	if len(queryer.args) != 4 || queryer.args[0] != "tenant-1" || queryer.args[1] != "project-1" || queryer.args[2] != "channel-1" || queryer.args[3] != "model-1" {
		t.Fatalf("resolver lost ownership inputs: %#v", queryer.args)
	}
	if target.APIKey != "sk-health-production" || target.ChannelID != "channel-1" || target.ModelID != "model-1" || !target.ExternalProviderOptIn || !target.SupportsTools || !target.SupportsJSON {
		t.Fatalf("unexpected target: %#v", target)
	}
}

func TestSQLHealthCredentialResolverRejectsMissingOrMalformedTargetWithoutSecretLeak(t *testing.T) {
	keyMaterial := strings.Repeat("9", 64)
	for _, test := range []struct {
		name string
		rows llm.SQLRows
	}{
		{name: "not-owned-or-disabled", rows: &healthResolverRows{}},
		{name: "bad-envelope", rows: &healthResolverRows{values: [][]any{{"channel-1", "model-1", "https://provider.example/v1", "sk-plaintext-must-not-leak", true, true, true}}}},
	} {
		t.Run(test.name, func(t *testing.T) {
			resolver, err := NewSQLHealthCredentialResolver(SQLHealthCredentialResolverConfig{Queryer: &healthResolverQueryer{rows: test.rows}, CredentialKeyMaterial: keyMaterial})
			if err != nil {
				t.Fatal(err)
			}
			_, err = resolver.ResolveHealthTarget(context.Background(), "tenant-1", "project-1", "channel-1", "model-1")
			if ErrorCode(err) != "LLM_PROVIDER_HEALTH_TARGET_UNAVAILABLE" || strings.Contains(err.Error(), "sk-plaintext") {
				t.Fatalf("unsafe resolver failure: %v", err)
			}
		})
	}
}
