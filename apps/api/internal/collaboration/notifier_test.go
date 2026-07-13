package collaboration

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

func TestSMTPNotifierDeliversTokenToRealSink(t *testing.T) {
	address, messages, closeSink := startSMTPSink(t)
	defer closeSink()
	host, portText, _ := net.SplitHostPort(address)
	port := 0
	for _, char := range portText {
		port = port*10 + int(char-'0')
	}
	notifier, err := NewSMTPNotifier(SMTPNotifierConfig{Host: host, Port: port, Username: "test-user", Password: "test-pass", From: "noreply@example.test", AcceptBaseURL: "http://localhost/invitations/accept", TLSMode: SMTPModeLoopbackPlaintext})
	if err != nil {
		t.Fatal(err)
	}
	_, err = notifier.SendInvitation(context.Background(), InvitationDelivery{Email: "writer@example.test", Token: "raw-invitation-token"})
	if err != nil {
		t.Fatalf("send invitation: %v", err)
	}
	select {
	case message := <-messages:
		if !strings.Contains(message, "token=raw-invitation-token") {
			t.Fatalf("SMTP body omitted invitation token: %s", message)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("SMTP sink did not receive invitation")
	}
}

func TestSMTPNotifierDeliversInvitationOverSTARTTLS(t *testing.T) {
	address, roots, messages, closeSink := startCollaborationSTARTTLSSink(t)
	defer closeSink()
	_, portText, _ := net.SplitHostPort(address)
	port, _ := strconv.Atoi(portText)
	notifier, err := NewSMTPNotifier(SMTPNotifierConfig{Host: "localhost", Port: port, Username: "test-user", Password: "test-pass", From: "noreply@example.test", AcceptBaseURL: "https://novel.example.test/invitations/accept", TLSMode: SMTPModeStartTLS, RootCAs: roots})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := notifier.SendInvitation(context.Background(), InvitationDelivery{Email: "writer@example.test", Token: "starttls-invitation-token"}); err != nil {
		t.Fatal(err)
	}
	select {
	case message := <-messages:
		if !strings.Contains(message, "token=starttls-invitation-token") {
			t.Fatalf("SMTP body omitted invitation token: %s", message)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("STARTTLS sink did not receive invitation")
	}
}

func TestSMTPNotifierRequiresCompleteExplicitConfiguration(t *testing.T) {
	valid := SMTPNotifierConfig{Host: "smtp.example.test", Port: 465, Username: "user", Password: "pass", From: "noreply@example.test", AcceptBaseURL: "https://novel.example.test/invitations/accept", TLSMode: SMTPModeImplicitTLS}
	valid.Password = ""
	if _, err := NewSMTPNotifier(valid); err == nil {
		t.Fatal("SMTP configuration without password was accepted")
	}
	valid.Password = "pass"
	valid.TLSMode = SMTPModeLoopbackPlaintext
	if _, err := NewSMTPNotifier(valid); err == nil {
		t.Fatal("plaintext SMTP was accepted for a non-loopback host")
	}
}

func TestInvitationTokensUseSHA256Digest(t *testing.T) {
	token, digest, err := newToken()
	if err != nil {
		t.Fatal(err)
	}
	if token == digest || len(digest) != 64 || hashToken(token) != digest {
		t.Fatalf("token was not represented by a SHA-256 digest")
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

func startCollaborationSTARTTLSSink(t *testing.T) (string, *x509.CertPool, <-chan string, func()) {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{SerialNumber: big.NewInt(2), Subject: pkix.Name{CommonName: "localhost"}, DNSNames: []string{"localhost"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	certificate, _ := x509.ParseCertificate(der)
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
		reader, writer := bufio.NewReader(conn), bufio.NewWriter(conn)
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
