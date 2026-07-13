package llm

import (
	"errors"
	"testing"
)

func TestTenantScopedWriteRowsCommitsOnlyAfterCleanExhaustion(t *testing.T) {
	rows := &writeRowsFixture{remaining: 1}
	tx := &transactionFinalizerFixture{}
	scoped := &tenantScopedWriteRows{rows: rows, tx: tx}

	if !scoped.Next() {
		t.Fatal("expected row")
	}
	var value string
	if err := scoped.Scan(&value); err != nil {
		t.Fatalf("scan row: %v", err)
	}
	if scoped.Next() {
		t.Fatal("expected clean exhaustion")
	}
	if err := scoped.Close(); err != nil {
		t.Fatalf("close clean write rows: %v", err)
	}
	if tx.commits != 1 || tx.rollbacks != 0 {
		t.Fatalf("clean exhaustion finalization mismatch: commits=%d rollbacks=%d", tx.commits, tx.rollbacks)
	}
}

func TestTenantScopedWriteRowsRollsBackOnScanFailure(t *testing.T) {
	rows := &writeRowsFixture{remaining: 1, scanErr: errors.New("scan failed")}
	tx := &transactionFinalizerFixture{}
	scoped := &tenantScopedWriteRows{rows: rows, tx: tx}

	if !scoped.Next() {
		t.Fatal("expected row")
	}
	var value string
	if err := scoped.Scan(&value); err == nil {
		t.Fatal("expected scan failure")
	}
	if err := scoped.Close(); err != nil {
		t.Fatalf("rollback after scan failure: %v", err)
	}
	assertWriteRollback(t, tx)
}

func TestTenantScopedWriteRowsRollsBackOnEarlyClose(t *testing.T) {
	rows := &writeRowsFixture{remaining: 1}
	tx := &transactionFinalizerFixture{}
	scoped := &tenantScopedWriteRows{rows: rows, tx: tx}

	if !scoped.Next() {
		t.Fatal("expected row before early close")
	}
	if err := scoped.Close(); err != nil {
		t.Fatalf("early close rollback: %v", err)
	}
	assertWriteRollback(t, tx)
}

func TestTenantScopedWriteRowsRollsBackOnRowsOrCloseError(t *testing.T) {
	for _, test := range []struct {
		name     string
		rowsErr  error
		closeErr error
	}{
		{name: "rows error", rowsErr: errors.New("rows failed")},
		{name: "close error", closeErr: errors.New("close failed")},
	} {
		t.Run(test.name, func(t *testing.T) {
			rows := &writeRowsFixture{rowsErr: test.rowsErr, closeErr: test.closeErr}
			tx := &transactionFinalizerFixture{}
			scoped := &tenantScopedWriteRows{rows: rows, tx: tx}
			if scoped.Next() {
				t.Fatal("unexpected row")
			}
			_ = scoped.Err()
			_ = scoped.Close()
			assertWriteRollback(t, tx)
		})
	}
}

func assertWriteRollback(t *testing.T, tx *transactionFinalizerFixture) {
	t.Helper()
	if tx.commits != 0 || tx.rollbacks != 1 {
		t.Fatalf("failed write finalization mismatch: commits=%d rollbacks=%d", tx.commits, tx.rollbacks)
	}
}

type transactionFinalizerFixture struct {
	commits   int
	rollbacks int
}

func (f *transactionFinalizerFixture) Commit() error {
	f.commits++
	return nil
}

func (f *transactionFinalizerFixture) Rollback() error {
	f.rollbacks++
	return nil
}

type writeRowsFixture struct {
	remaining int
	scanErr   error
	rowsErr   error
	closeErr  error
}

func (f *writeRowsFixture) Next() bool { return f.remaining > 0 }

func (f *writeRowsFixture) Scan(dest ...any) error {
	if f.scanErr != nil {
		return f.scanErr
	}
	if f.remaining <= 0 {
		return errors.New("scan past end")
	}
	f.remaining--
	if len(dest) > 0 {
		if value, ok := dest[0].(*string); ok {
			*value = "ok"
		}
	}
	return nil
}

func (f *writeRowsFixture) Close() error { return f.closeErr }
func (f *writeRowsFixture) Err() error   { return f.rowsErr }
