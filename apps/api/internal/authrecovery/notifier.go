package authrecovery

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
	Host                                                        string
	Port                                                        int
	Username, Password, From, ResetBaseURL, VerificationBaseURL string
	TLSMode                                                     string
	RootCAs                                                     *x509.CertPool
}
type SMTPNotifier struct{ config SMTPNotifierConfig }

const (
	SMTPModeImplicitTLS       = "implicit_tls"
	SMTPModeStartTLS          = "starttls"
	SMTPModeLoopbackPlaintext = "loopback_plaintext_test_only"
)

func NewSMTPNotifier(config SMTPNotifierConfig) (*SMTPNotifier, error) {
	if strings.TrimSpace(config.Host) == "" || config.Port <= 0 || strings.TrimSpace(config.Username) == "" || strings.TrimSpace(config.Password) == "" || strings.TrimSpace(config.From) == "" || (strings.TrimSpace(config.ResetBaseURL) == "" && strings.TrimSpace(config.VerificationBaseURL) == "") || strings.TrimSpace(config.TLSMode) == "" {
		return nil, &AppError{Code: CodeBackendUnavailable, Message: "SMTP password recovery is not configured"}
	}
	if config.ResetBaseURL != "" {
		if err := validatePublicURL(config.ResetBaseURL); err != nil {
			return nil, &AppError{Code: CodeValidationFailed, Message: "password reset URL is invalid"}
		}
	}
	if config.VerificationBaseURL != "" {
		if err := validatePublicURL(config.VerificationBaseURL); err != nil {
			return nil, &AppError{Code: CodeValidationFailed, Message: "email verification URL is invalid"}
		}
	}
	if config.ResetBaseURL == "" && config.VerificationBaseURL == "" {
		return nil, &AppError{Code: CodeValidationFailed, Message: "password reset URL is invalid"}
	}
	if config.TLSMode != SMTPModeImplicitTLS && config.TLSMode != SMTPModeStartTLS && (config.TLSMode != SMTPModeLoopbackPlaintext || !isLoopbackHost(config.Host)) {
		return nil, &AppError{Code: CodeValidationFailed, Message: "SMTP TLS mode is invalid"}
	}
	return &SMTPNotifier{config: config}, nil
}
func (n *SMTPNotifier) SendPasswordReset(ctx context.Context, input ResetDelivery) (DeliveryReceipt, error) {
	return n.sendLink(ctx, n.config.ResetBaseURL, input.Email, input.Token, "MiroFish Novel password reset")
}

func (n *SMTPNotifier) SendEmailVerification(ctx context.Context, input EmailVerificationDelivery) (DeliveryReceipt, error) {
	return n.sendLink(ctx, n.config.VerificationBaseURL, input.Email, input.Token, "MiroFish Novel email verification")
}

func (n *SMTPNotifier) sendLink(ctx context.Context, baseURL, recipient, token, subject string) (DeliveryReceipt, error) {
	link, err := url.Parse(baseURL)
	if err != nil {
		return DeliveryReceipt{}, err
	}
	query := link.Query()
	query.Set("token", token)
	link.RawQuery = query.Encode()
	message := []byte("To: " + recipient + "\r\nFrom: " + n.config.From + "\r\nSubject: " + subject + "\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\nOpen this link: " + link.String() + "\r\n")
	address := net.JoinHostPort(n.config.Host, strconv.Itoa(n.config.Port))
	if n.config.TLSMode == SMTPModeImplicitTLS {
		return DeliveryReceipt{}, n.sendTLS(ctx, address, recipient, message)
	}
	if n.config.TLSMode == SMTPModeStartTLS {
		return DeliveryReceipt{}, n.sendSTARTTLS(ctx, address, recipient, message)
	}
	if err := smtp.SendMail(address, nil, n.config.From, []string{recipient}, message); err != nil {
		return DeliveryReceipt{}, fmt.Errorf("SMTP email delivery failed: %w", err)
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
	return net.ParseIP(trimmed) != nil && net.ParseIP(trimmed).IsLoopback()
}
func (n *SMTPNotifier) sendTLS(ctx context.Context, address, recipient string, message []byte) error {
	dialer := tls.Dialer{Config: n.tlsConfig()}
	conn, err := dialer.DialContext(ctx, "tcp", address)
	if err != nil {
		return err
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
		return err
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
