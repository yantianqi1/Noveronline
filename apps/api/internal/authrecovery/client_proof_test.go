package authrecovery

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"strconv"
	"testing"
	"time"
)

func TestClientProofVerifierAcceptsOnlyFreshSignedClientHash(t *testing.T) {
	secret := []byte("0123456789abcdef0123456789abcdef")
	now := time.Date(2026, 7, 11, 1, 0, 0, 0, time.UTC)
	verifier, err := NewClientProofVerifier(secret, func() time.Time { return now }, 2*time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	clientHash := hashToken("203.0.113.7")
	timestamp := strconv.FormatInt(now.Unix(), 10)
	message := "v1:" + timestamp + ":" + clientHash
	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write([]byte(message))
	proof := message + ":" + hex.EncodeToString(mac.Sum(nil))
	got, err := verifier.Verify(proof)
	if err != nil || got != clientHash {
		t.Fatalf("hash=%q err=%v", got, err)
	}
	if _, err := verifier.Verify(proof[:len(proof)-1] + "0"); err == nil {
		t.Fatal("tampered proof was accepted")
	}
	if _, err := verifier.Verify("v1:1:" + clientHash + ":" + proof[len(proof)-64:]); err == nil {
		t.Fatal("expired proof was accepted")
	}
}
