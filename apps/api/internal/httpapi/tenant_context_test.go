package httpapi

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"mirofish-novel/apps/api/internal/auth"
)

type tenantContextReader struct {
	user auth.CurrentUser
}

func (r tenantContextReader) GetCurrentUser(context.Context, auth.GetCurrentUserInput) (auth.CurrentUser, error) {
	return r.user, nil
}

func TestTenantHeaderMustBelongToResolvedActor(t *testing.T) {
	server := newDevelopmentServer(Config{AuthReader: tenantContextReader{user: auth.CurrentUser{
		ActiveTenants: []auth.TenantMembershipSummary{{TenantID: "tenant-a", Status: "active"}},
	}}})
	request := httptest.NewRequest(http.MethodGet, "/v1/llm/settings", nil)
	request.Header.Set("X-User-Id", "user-a")
	request.Header.Set("X-Tenant-Id", "tenant-b")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusForbidden {
		t.Fatalf("forged tenant header status=%d body=%s", response.Code, response.Body.String())
	}
}
