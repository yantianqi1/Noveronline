package authrecovery

import (
	"bufio"
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"math/big"
	"net"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestSMTPNotifierDeliversResetTokenToRealSink(t *testing.T) {
	address, messages, closeSink := startSMTPSink(t)
	defer closeSink()
	host, portText, _ := net.SplitHostPort(address)
	port, _ := strconv.Atoi(portText)
	notifier, err := NewSMTPNotifier(SMTPNotifierConfig{Host: host, Port: port, Username: "test-user", Password: "test-pass", From: "security@example.test", ResetBaseURL: "http://localhost/recovery/reset", TLSMode: SMTPModeLoopbackPlaintext})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = notifier.SendPasswordReset(context.Background(), ResetDelivery{Email: "user@example.test", Token: "raw-reset-token"}); err != nil {
		t.Fatalf("send reset: %v", err)
	}
	select {
	case message := <-messages:
		if !strings.Contains(message, "token=raw-reset-token") {
			t.Fatalf("SMTP body omitted reset token: %s", message)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("SMTP sink did not receive reset")
	}
}

func TestSMTPNotifierDeliversOverSTARTTLS(t *testing.T) {
	address, roots, messages, closeSink := startSTARTTLSSink(t)
	defer closeSink()
	_, portText, _ := net.SplitHostPort(address)
	port, _ := strconv.Atoi(portText)
	notifier, err := NewSMTPNotifier(SMTPNotifierConfig{Host: "localhost", Port: port, Username: "test-user", Password: "test-pass", From: "security@example.test", ResetBaseURL: "https://novel.example.test/recovery/reset", TLSMode: SMTPModeStartTLS, RootCAs: roots})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := notifier.SendPasswordReset(context.Background(), ResetDelivery{Email: "user@example.test", Token: "starttls-reset-token"}); err != nil {
		t.Fatal(err)
	}
	select {
	case message := <-messages:
		if !strings.Contains(message, "token=starttls-reset-token") {
			t.Fatalf("SMTP body omitted reset token: %s", message)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("STARTTLS sink did not receive reset")
	}
}

func TestSMTPNotifierRequiresCompleteExplicitConfiguration(t *testing.T) {
	valid := SMTPNotifierConfig{Host: "smtp.example.test", Port: 465, Username: "user", Password: "pass", From: "security@example.test", ResetBaseURL: "https://novel.example.test/recovery/reset", TLSMode: SMTPModeImplicitTLS}
	cases := []struct {
		name string
		edit func(*SMTPNotifierConfig)
	}{
		{"host", func(c *SMTPNotifierConfig) { c.Host = "" }},
		{"port", func(c *SMTPNotifierConfig) { c.Port = 0 }},
		{"username", func(c *SMTPNotifierConfig) { c.Username = "" }},
		{"password", func(c *SMTPNotifierConfig) { c.Password = "" }},
		{"from", func(c *SMTPNotifierConfig) { c.From = "" }},
		{"reset URL", func(c *SMTPNotifierConfig) { c.ResetBaseURL = "" }},
		{"TLS mode", func(c *SMTPNotifierConfig) { c.TLSMode = "" }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			config := valid
			tc.edit(&config)
			if _, err := NewSMTPNotifier(config); err == nil {
				t.Fatal("incomplete SMTP configuration was accepted")
			}
		})
	}
	valid.ResetBaseURL = "http://novel.example.test/recovery/reset"
	if _, err := NewSMTPNotifier(valid); err == nil {
		t.Fatal("non-HTTPS public reset URL was accepted")
	}
}
func TestResetTokensUseSHA256Digest(t *testing.T) {
	token, digest, err := newToken()
	if err != nil {
		t.Fatal(err)
	}
	if token == digest || len(digest) != 64 || hashToken(token) != digest {
		t.Fatal("reset token was not represented by a SHA-256 digest")
	}
}
func TestGenericRequestMessageDoesNotClaimDelivery(t *testing.T) {
	lower := strings.ToLower(genericRequestMessage)
	if strings.Contains(lower, "sent") || strings.Contains(lower, "delivered") || !strings.Contains(lower, "attempt") {
		t.Fatal("generic response claimed delivery")
	}
}

func startSMTPSink(t *testing.T) (string, <-chan string, func()) {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	messages := make(chan string, 1)
	done := make(chan struct{})
	go func() {
		defer close(done)
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		reader := bufio.NewReader(conn)
		writer := bufio.NewWriter(conn)
		write := func(line string) { _, _ = writer.WriteString(line + "\r\n"); _ = writer.Flush() }
		write("220 localhost test-smtp")
		inData := false
		var body strings.Builder
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				return
			}
			trimmed := strings.TrimRight(line, "\r\n")
			if inData {
				if trimmed == "." {
					messages <- body.String()
					write("250 queued")
					inData = false
				} else {
					body.WriteString(trimmed)
					body.WriteByte('\n')
				}
				continue
			}
			upper := strings.ToUpper(trimmed)
			switch {
			case strings.HasPrefix(upper, "EHLO"), strings.HasPrefix(upper, "HELO"):
				write("250 localhost")
			case strings.HasPrefix(upper, "MAIL FROM"), strings.HasPrefix(upper, "RCPT TO"):
				write("250 ok")
			case upper == "DATA":
				write("354 end with dot")
				inData = true
			case upper == "QUIT":
				write("221 bye")
				return
			default:
				write("250 ok")
			}
		}
	}()
	return listener.Addr().String(), messages, func() { _ = listener.Close(); <-done }
}

func startSTARTTLSSink(t *testing.T) (string, *x509.CertPool, <-chan string, func()) {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "localhost"}, DNSNames: []string{"localhost"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	certificate, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	roots := x509.NewCertPool()
	roots.AddCert(certificate)
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	messages := make(chan string, 1)
	done := make(chan struct{})
	go func() {
		defer close(done)
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		reader := bufio.NewReader(conn)
		writer := bufio.NewWriter(conn)
		write := func(line string) { _, _ = writer.WriteString(line + "\r\n"); _ = writer.Flush() }
		write("220 localhost test-smtp")
		encrypted, inData := false, false
		var body strings.Builder
		for {
			line, err := reader.ReadString('\n')
			if err != nil {
				return
			}
			trimmed := strings.TrimRight(line, "\r\n")
			if inData {
				if trimmed == "." {
					messages <- body.String()
					write("250 queued")
					inData = false
				} else {
					body.WriteString(trimmed)
					body.WriteByte('\n')
				}
				continue
			}
			upper := strings.ToUpper(trimmed)
			switch {
			case strings.HasPrefix(upper, "EHLO"), strings.HasPrefix(upper, "HELO"):
				if encrypted {
					_, _ = writer.WriteString("250-localhost\r\n250 AUTH PLAIN\r\n")
				} else {
					_, _ = writer.WriteString("250-localhost\r\n250-STARTTLS\r\n250 AUTH PLAIN\r\n")
				}
				_ = writer.Flush()
			case upper == "STARTTLS":
				write("220 ready to start TLS")
				tlsConn := tls.Server(conn, &tls.Config{Certificates: []tls.Certificate{{Certificate: [][]byte{der}, PrivateKey: key}}, MinVersion: tls.VersionTLS12})
				if tlsConn.Handshake() != nil {
					return
				}
				conn, encrypted = tlsConn, true
				reader, writer = bufio.NewReader(conn), bufio.NewWriter(conn)
			case strings.HasPrefix(upper, "AUTH PLAIN"):
				write("235 authenticated")
			case strings.HasPrefix(upper, "MAIL FROM"), strings.HasPrefix(upper, "RCPT TO"):
				write("250 ok")
			case upper == "DATA":
				write("354 end with dot")
				inData = true
			case upper == "QUIT":
				write("221 bye")
				return
			default:
				write("250 ok")
			}
		}
	}()
	return listener.Addr().String(), roots, messages, func() { _ = listener.Close(); <-done }
}
