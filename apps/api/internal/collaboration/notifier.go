package collaboration

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"net"
	"net/smtp"
	"net/url"
	"strconv"
	"strings"
)

type SMTPNotifierConfig struct {
	Host          string
	Port          int
	Username      string
	Password      string
	From          string
	AcceptBaseURL string
	TLSMode       string
	RootCAs       *x509.CertPool
}

type SMTPNotifier struct{ config SMTPNotifierConfig }

const (
	SMTPModeImplicitTLS       = "implicit_tls"
	SMTPModeStartTLS          = "starttls"
	SMTPModeLoopbackPlaintext = "loopback_plaintext_test_only"
)

func NewSMTPNotifier(config SMTPNotifierConfig) (*SMTPNotifier, error) {
	if strings.TrimSpace(config.Host) == "" || config.Port <= 0 || strings.TrimSpace(config.Username) == "" || strings.TrimSpace(config.Password) == "" || strings.TrimSpace(config.From) == "" || strings.TrimSpace(config.AcceptBaseURL) == "" || strings.TrimSpace(config.TLSMode) == "" {
		return nil, &AppError{Code: CodeDeliveryUnavailable, Message: "SMTP invitation delivery is not configured"}
	}
	if err := validatePublicURL(config.AcceptBaseURL); err != nil {
		return nil, &AppError{Code: CodeValidationFailed, Message: "invitation accept URL is invalid"}
	}
	if config.TLSMode != SMTPModeImplicitTLS && config.TLSMode != SMTPModeStartTLS && (config.TLSMode != SMTPModeLoopbackPlaintext || !isLoopbackHost(config.Host)) {
		return nil, &AppError{Code: CodeValidationFailed, Message: "SMTP TLS mode is invalid"}
	}
	return &SMTPNotifier{config: config}, nil
}

func (n *SMTPNotifier) SendInvitation(ctx context.Context, input InvitationDelivery) (DeliveryReceipt, error) {
	acceptURL, err := url.Parse(n.config.AcceptBaseURL)
	if err != nil {
		return DeliveryReceipt{}, err
	}
	query := acceptURL.Query()
	query.Set("token", input.Token)
	acceptURL.RawQuery = query.Encode()
	body := "You have been invited to MiroFish Novel.\r\n\r\nAccept invitation: " + acceptURL.String() + "\r\n"
	message := []byte("To: " + input.Email + "\r\nFrom: " + n.config.From + "\r\nSubject: MiroFish Novel invitation\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n" + body)
	address := net.JoinHostPort(n.config.Host, strconv.Itoa(n.config.Port))
	if n.config.TLSMode == SMTPModeImplicitTLS {
		return DeliveryReceipt{}, n.sendTLS(ctx, address, input.Email, message)
	}
	if n.config.TLSMode == SMTPModeStartTLS {
		return DeliveryReceipt{}, n.sendSTARTTLS(ctx, address, input.Email, message)
	}
	if err := smtp.SendMail(address, nil, n.config.From, []string{input.Email}, message); err != nil {
		return DeliveryReceipt{}, fmt.Errorf("SMTP invitation delivery failed: %w", err)
	}
	return DeliveryReceipt{}, nil
}

func validatePublicURL(raw string) error {
	parsed, err := url.ParseRequestURI(raw)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil || parsed.Fragment != "" {
		return fmt.Errorf("invalid public URL")
	}
	if parsed.Scheme != "https" && !(parsed.Scheme == "http" && isLoopbackHost(parsed.Hostname())) {
		return fmt.Errorf("public URL must use HTTPS")
	}
	return nil
}

func isLoopbackHost(host string) bool {
	trimmed := strings.Trim(strings.TrimSpace(host), "[]")
	if strings.EqualFold(trimmed, "localhost") {
		return true
	}
	parsed := net.ParseIP(trimmed)
	return parsed != nil && parsed.IsLoopback()
}

func (n *SMTPNotifier) sendTLS(ctx context.Context, address, recipient string, message []byte) error {
	dialer := &tls.Dialer{Config: n.tlsConfig()}
	conn, err := dialer.DialContext(ctx, "tcp", address)
	if err != nil {
		return fmt.Errorf("SMTP TLS connection failed: %w", err)
	}
	defer conn.Close()
	client, err := smtp.NewClient(conn, n.config.Host)
	if err != nil {
		return err
	}
	defer client.Close()
	if n.config.Username != "" {
		if err := client.Auth(smtp.PlainAuth("", n.config.Username, n.config.Password, n.config.Host)); err != nil {
			return err
		}
	}
	if err := client.Mail(n.config.From); err != nil {
		return err
	}
	if err := client.Rcpt(recipient); err != nil {
		return err
	}
	writer, err := client.Data()
	if err != nil {
		return err
	}
	if _, err := writer.Write(message); err != nil {
		return err
	}
	if err := writer.Close(); err != nil {
		return err
	}
	return client.Quit()
}

func (n *SMTPNotifier) sendSTARTTLS(ctx context.Context, address, recipient string, message []byte) error {
	conn, err := (&net.Dialer{}).DialContext(ctx, "tcp", address)
	if err != nil {
		return fmt.Errorf("SMTP STARTTLS connection failed: %w", err)
	}
	defer conn.Close()
	client, err := smtp.NewClient(conn, n.config.Host)
	if err != nil {
		return err
	}
	defer client.Close()
	if ok, _ := client.Extension("STARTTLS"); !ok {
		return fmt.Errorf("SMTP server does not support STARTTLS")
	}
	if err := client.StartTLS(n.tlsConfig()); err != nil {
		return err
	}
	if err := client.Auth(smtp.PlainAuth("", n.config.Username, n.config.Password, n.config.Host)); err != nil {
		return err
	}
	if err := client.Mail(n.config.From); err != nil {
		return err
	}
	if err := client.Rcpt(recipient); err != nil {
		return err
	}
	writer, err := client.Data()
	if err != nil {
		return err
	}
	if _, err := writer.Write(message); err != nil {
		return err
	}
	if err := writer.Close(); err != nil {
		return err
	}
	return client.Quit()
}

func (n *SMTPNotifier) tlsConfig() *tls.Config {
	return &tls.Config{ServerName: n.config.Host, MinVersion: tls.VersionTLS12, RootCAs: n.config.RootCAs}
}
