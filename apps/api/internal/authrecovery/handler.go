package authrecovery

import (
	"encoding/json"
	"net/http"
	"strings"
)

type HandlerConfig struct {
	Service             *Service
	ClientProofVerifier *ClientProofVerifier
}

type Handler struct {
	service             *Service
	clientProofVerifier *ClientProofVerifier
}

func NewHandler(config HandlerConfig) *Handler {
	return &Handler{service: config.Service, clientProofVerifier: config.ClientProofVerifier}
}
func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimSuffix(r.URL.Path, "/")
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "METHOD_NOT_ALLOWED", "method is not allowed", requestID(r))
		return
	}
	if path != "/v1/auth/recovery/request" && path != "/v1/auth/recovery/reset" {
		writeError(w, http.StatusNotFound, "NOT_FOUND", "password recovery route not found", requestID(r))
		return
	}
	clientKey, ok := h.verifiedClient(w, r)
	if !ok {
		return
	}
	switch path {
	case "/v1/auth/recovery/request":
		h.request(w, r, clientKey)
	case "/v1/auth/recovery/reset":
		h.reset(w, r)
	}
}
func (h *Handler) verifiedClient(w http.ResponseWriter, r *http.Request) (string, bool) {
	if h.clientProofVerifier == nil {
		writeError(w, http.StatusServiceUnavailable, CodeBackendUnavailable, "password recovery client verification is not configured", requestID(r))
		return "", false
	}
	clientKey, err := h.clientProofVerifier.Verify(r.Header.Get(RecoveryClientProofHeader))
	if err != nil {
		writeError(w, http.StatusForbidden, "AUTH_RECOVERY_CLIENT_PROOF_INVALID", "password recovery client verification failed", requestID(r))
		return "", false
	}
	return clientKey, true
}
func (h *Handler) request(w http.ResponseWriter, r *http.Request, clientKey string) {
	if h.service == nil {
		writeError(w, http.StatusServiceUnavailable, CodeBackendUnavailable, "password recovery backend is not configured", requestID(r))
		return
	}
	var body struct {
		Email string `json:"email"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	result, err := h.service.RequestReset(r.Context(), RequestResetInput{Email: body.Email, RequestID: requestID(r), ClientKey: clientKey})
	if err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusAccepted, result)
}
func (h *Handler) reset(w http.ResponseWriter, r *http.Request) {
	if h.service == nil {
		writeError(w, http.StatusServiceUnavailable, CodeBackendUnavailable, "password recovery backend is not configured", requestID(r))
		return
	}
	var body struct {
		Token       string `json:"token"`
		NewPassword string `json:"new_password"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	if err := h.service.CompleteReset(r.Context(), CompleteResetInput{Token: body.Token, NewPassword: body.NewPassword, RequestID: requestID(r)}); err != nil {
		writeDomainError(w, err, requestID(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}
func decodeJSON(w http.ResponseWriter, r *http.Request, target any) bool {
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 32<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		writeError(w, http.StatusBadRequest, CodeValidationFailed, "request body is invalid", requestID(r))
		return false
	}
	return true
}
func writeDomainError(w http.ResponseWriter, err error, requestID string) {
	status := http.StatusInternalServerError
	code := ErrorCode(err)
	switch code {
	case CodeValidationFailed:
		status = http.StatusBadRequest
	case CodeTokenInvalid:
		status = http.StatusNotFound
	case CodeTokenExpired, CodeTokenConsumed:
		status = http.StatusConflict
	case CodeRateLimited:
		status = http.StatusTooManyRequests
	}
	writeError(w, status, code, err.Error(), requestID)
}
func writeError(w http.ResponseWriter, status int, code, message, requestID string) {
	writeJSON(w, status, map[string]any{"ok": false, "error": map[string]string{"code": code, "message": message, "request_id": requestID}})
}
func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
func requestID(r *http.Request) string { return strings.TrimSpace(r.Header.Get("X-Request-Id")) }
