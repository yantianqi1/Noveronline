package llmadmin

import (
	"context"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type staticHealthResolver struct {
	addresses []net.IPAddr
	err       error
}

func (r staticHealthResolver) LookupIPAddr(context.Context, string) ([]net.IPAddr, error) {
	return r.addresses, r.err
}

func TestHTTPHealthExecutorRejectsExternalDNSResolvingToSensitiveNetworks(t *testing.T) {
	for _, address := range []string{"127.0.0.1", "10.0.0.8", "169.254.169.254", "0.0.0.0", "224.0.0.1"} {
		executor := NewHTTPHealthExecutor(&http.Client{Transport: http.DefaultTransport}, time.Second, 1024)
		executor.resolver = staticHealthResolver{addresses: []net.IPAddr{{IP: net.ParseIP(address)}}}
		_, err := executor.ExecuteHealth(context.Background(), HealthRequest{
			BaseURL: "https://provider.example/v1", APIKey: "secret", ModelID: "model",
			ExternalProviderOptIn: true, ProviderCallID: "call-1", Body: []byte(`{"model":"model"}`),
		})
		if ErrorCode(err) != "LLM_PROVIDER_NETWORK_TARGET_FORBIDDEN" {
			t.Fatalf("sensitive resolved address %s was accepted: %v", address, err)
		}
	}
}

func TestHTTPHealthExecutorPinsDialToValidatedResolvedIP(t *testing.T) {
	executor := NewHTTPHealthExecutor(&http.Client{Transport: http.DefaultTransport}, time.Second, 1024)
	executor.resolver = staticHealthResolver{addresses: []net.IPAddr{{IP: net.ParseIP("93.184.216.34")}}}
	var dialed string
	executor.dialContext = func(_ context.Context, _, address string) (net.Conn, error) {
		dialed = address
		return nil, errors.New("test dial stop")
	}
	_, _ = executor.ExecuteHealth(context.Background(), HealthRequest{
		BaseURL: "https://provider.example/v1", APIKey: "secret", ModelID: "model",
		ExternalProviderOptIn: true, ProviderCallID: "call-1", Body: []byte(`{"model":"model"}`),
	})
	if !strings.HasPrefix(dialed, "93.184.216.34:") || strings.Contains(dialed, "provider.example") {
		t.Fatalf("dial was not pinned to the validated IP: %q", dialed)
	}
}

func TestHTTPHealthExecutorNeverFollowsProviderRedirects(t *testing.T) {
	redirected := 0
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if request.URL.Path == "/redirected" {
			redirected++
			if request.Header.Get("Authorization") != "" {
				t.Errorf("redirect target received bearer credential")
			}
			response.WriteHeader(http.StatusOK)
			return
		}
		http.Redirect(response, request, "/redirected", http.StatusFound)
	}))
	defer server.Close()
	executor := NewHTTPHealthExecutor(server.Client(), time.Second, 1024)
	result, err := executor.ExecuteHealth(context.Background(), HealthRequest{
		BaseURL: server.URL, APIKey: "secret", ModelID: "model", ProviderCallID: "call-1", Body: []byte(`{"model":"model"}`),
	})
	if err != nil || result.StatusCode != http.StatusFound || redirected != 0 {
		t.Fatalf("redirect was followed: result=%#v redirected=%d err=%v", result, redirected, err)
	}
}

func TestHealthEndpointLocalHTTPRequiresExplicitLoopback(t *testing.T) {
	for _, baseURL := range []string{"http://host.docker.internal/v1", "http://provider-service/v1", "http://10.0.0.8/v1"} {
		if code := ErrorCode(validateHealthEndpoint(baseURL, true)); code != "LLM_EXTERNAL_PROVIDER_HTTPS_REQUIRED" {
			t.Fatalf("non-loopback local HTTP target %q accepted: %s", baseURL, code)
		}
	}
	for _, baseURL := range []string{"http://localhost:8080/v1", "http://127.0.0.1:8080/v1", "http://[::1]:8080/v1"} {
		if err := validateHealthEndpoint(baseURL, false); err != nil {
			t.Fatalf("explicit loopback target %q rejected: %v", baseURL, err)
		}
	}
}
