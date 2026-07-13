package authrecovery

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"errors"
	"io"
)

type TokenCipher struct{ aead cipher.AEAD }

func NewTokenCipher(key []byte) (*TokenCipher, error) {
	if len(key) != 32 {
		return nil, errors.New("auth recovery outbox encryption key must be 32 bytes")
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	return &TokenCipher{aead: aead}, nil
}

func (c *TokenCipher) Encrypt(plaintext []byte) ([]byte, error) {
	return c.EncryptForScope(plaintext, "")
}

func (c *TokenCipher) EncryptForScope(plaintext []byte, scope string) ([]byte, error) {
	if c == nil || c.aead == nil {
		return nil, errors.New("auth recovery token cipher is not configured")
	}
	nonce := make([]byte, c.aead.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, err
	}
	return c.aead.Seal(nonce, nonce, plaintext, []byte(scope)), nil
}

func (c *TokenCipher) Decrypt(ciphertext []byte) ([]byte, error) {
	return c.DecryptForScope(ciphertext, "")
}

func (c *TokenCipher) DecryptForScope(ciphertext []byte, scope string) ([]byte, error) {
	if c == nil || c.aead == nil || len(ciphertext) < c.aead.NonceSize() {
		return nil, errors.New("auth recovery token ciphertext is invalid")
	}
	nonce := ciphertext[:c.aead.NonceSize()]
	return c.aead.Open(nil, nonce, ciphertext[c.aead.NonceSize():], []byte(scope))
}
