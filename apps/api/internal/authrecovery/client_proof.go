package authrecovery

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strconv"
	"strings"
	"time"
)

const RecoveryClientProofHeader = "X-Mirofish-Recovery-Client"

type ClientProofVerifier struct {
	secret []byte
	now    func() time.Time
	maxAge time.Duration
}

func NewClientProofVerifier(secret []byte, now func() time.Time, maxAge time.Duration) (*ClientProofVerifier, error) {
	if len(secret) < 32 {
		return nil, errors.New("recovery client proof secret must be at least 32 bytes")
	}
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	if maxAge <= 0 {
		maxAge = 2 * time.Minute
	}
	return &ClientProofVerifier{secret: append([]byte(nil), secret...), now: now, maxAge: maxAge}, nil
}

func (v *ClientProofVerifier) Verify(proof string) (string, error) {
	if v == nil {
		return "", errors.New("recovery client proof verifier is not configured")
	}
	parts := strings.Split(strings.TrimSpace(proof), ":")
	if len(parts) != 4 || parts[0] != "v1" || len(parts[2]) != 64 || len(parts[3]) != 64 {
		return "", errors.New("recovery client proof is invalid")
	}
	if _, err := hex.DecodeString(parts[2]); err != nil {
		return "", errors.New("recovery client hash is invalid")
	}
	timestamp, err := strconv.ParseInt(parts[1], 10, 64)
	if err != nil {
		return "", errors.New("recovery client proof timestamp is invalid")
	}
	age := v.now().Sub(time.Unix(timestamp, 0))
	if age < -v.maxAge || age > v.maxAge {
		return "", errors.New("recovery client proof has expired")
	}
	message := strings.Join(parts[:3], ":")
	mac := hmac.New(sha256.New, v.secret)
	_, _ = mac.Write([]byte(message))
	expected := hex.EncodeToString(mac.Sum(nil))
	if !hmac.Equal([]byte(expected), []byte(parts[3])) {
		return "", errors.New("recovery client proof signature is invalid")
	}
	return parts[2], nil
}
