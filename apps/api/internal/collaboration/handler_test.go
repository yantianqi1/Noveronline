package collaboration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

type countingActorResolver struct{ calls int }

func (r *countingActorResolver) ResolveActor(context.Context, *http.Request) (string, error) {
	r.calls++
	return "actor", nil
}

type countingCSRFVerifier struct{ calls int }

func (v *countingCSRFVerifier) VerifyCSRF(context.Context, *http.Request) error {
	v.calls++
	return nil
}

func TestMalformedDoubleSlashRoutesAreRejectedBeforeSecurityOrServiceWork(t *testing.T) {
	actor := &countingActorResolver{}
	csrf := &countingCSRFVerifier{}
	handler := NewHandler(HandlerConfig{Service: NewService(ServiceConfig{}), ActorResolver: actor, CSRFVerifier: csrf})
	paths := []string{
		"/v1/collaboration/invitations//accept",
		"/v1/tenants/tenant//invitations",
		"/v1/tenants/tenant/projects/project//members",
	}
	for _, path := range paths {
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodPost, path, nil))
		if recorder.Code != http.StatusNotFound {
			t.Fatalf("path %q status=%d", path, recorder.Code)
		}
	}
	if actor.calls != 0 || csrf.calls != 0 {
		t.Fatalf("malformed paths reached security dependencies: actor=%d csrf=%d", actor.calls, csrf.calls)
	}
}

func TestEveryMutationIncludingAcceptRequiresCSRFBeforeDecodeOrStore(t *testing.T) {
	actor := &countingActorResolver{}
	handler := NewHandler(HandlerConfig{Service: NewService(ServiceConfig{}), ActorResolver: actor})
	cases := []struct {
		method string
		path   string
	}{
		{http.MethodPost, "/v1/collaboration/invitations/accept"},
		{http.MethodPost, "/v1/tenants/tenant/invitations"},
		{http.MethodPost, "/v1/tenants/tenant/invitations/invitation/resend"},
		{http.MethodDelete, "/v1/tenants/tenant/invitations/invitation"},
		{http.MethodPatch, "/v1/tenants/tenant/members/user"},
		{http.MethodDelete, "/v1/tenants/tenant/members/user"},
		{http.MethodPatch, "/v1/tenants/tenant/projects/project/members/user"},
		{http.MethodDelete, "/v1/tenants/tenant/projects/project/members/user"},
	}
	for _, tc := range cases {
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, httptest.NewRequest(tc.method, tc.path, nil))
		if recorder.Code != http.StatusForbidden {
			t.Fatalf("%s %s status=%d body=%s", tc.method, tc.path, recorder.Code, recorder.Body.String())
		}
	}
	if actor.calls != len(cases) {
		t.Fatalf("actor calls=%d want=%d", actor.calls, len(cases))
	}
}
