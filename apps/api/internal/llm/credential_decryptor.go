package llm

import "strings"

// CredentialDecryptor keeps parsed encryption key material in process memory and
// only accepts the versioned AES-GCM envelope written by SQLChannelStore.
type CredentialDecryptor struct {
	key []byte
}

func NewCredentialDecryptor(keyMaterial string) (*CredentialDecryptor, error) {
	key, err := parseCredentialKey(keyMaterial)
	if err != nil {
		return nil, err
	}
	if len(key) == 0 {
		return nil, &AppError{
			Code:    "LLM_CREDENTIAL_ENCRYPTION_UNCONFIGURED",
			Message: "LLM credential encryption key is not configured",
		}
	}
	return &CredentialDecryptor{key: append([]byte(nil), key...)}, nil
}

func (d *CredentialDecryptor) Decrypt(envelope string) (string, error) {
	if d == nil || len(d.key) != 32 {
		return "", &AppError{
			Code:    "LLM_CREDENTIAL_ENCRYPTION_UNCONFIGURED",
			Message: "LLM credential encryption key is not configured",
		}
	}
	plaintext, err := decryptCredentialEnvelope(envelope, d.key)
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(plaintext) == "" {
		return "", &AppError{
			Code:    "LLM_CREDENTIAL_DECRYPTION_FAILED",
			Message: "credential decrypt failed",
		}
	}
	return plaintext, nil
}
