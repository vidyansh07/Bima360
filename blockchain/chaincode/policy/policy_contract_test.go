package main

import (
	"encoding/json"
	"testing"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
)

// MockTransactionContext mocks the Fabric transaction context for testing.
type MockTransactionContext struct {
	mock.Mock
	contractapi.TransactionContextInterface
	stub *MockStub
}

func (m *MockTransactionContext) GetStub() contractapi.ChaincodeStubInterface {
	return m.stub
}

type MockStub struct {
	mock.Mock
	contractapi.ChaincodeStubInterface
	state map[string][]byte
}

func newMockStub() *MockStub {
	return &MockStub{state: make(map[string][]byte)}
}

func (s *MockStub) GetState(key string) ([]byte, error) {
	val, ok := s.state[key]
	if !ok {
		return nil, nil
	}
	return val, nil
}

func (s *MockStub) PutState(key string, value []byte) error {
	s.state[key] = value
	return nil
}

func (s *MockStub) CreateCompositeKey(objectType string, attributes []string) (string, error) {
	key := objectType
	for _, a := range attributes {
		key += "\x00" + a
	}
	return key, nil
}

func (s *MockStub) SplitCompositeKey(compositeKey string) (string, []string, error) {
	return "", nil, nil
}

func (s *MockStub) SetEvent(name string, payload []byte) error {
	return nil
}

func newCtx() *MockTransactionContext {
	ctx := &MockTransactionContext{stub: newMockStub()}
	return ctx
}

// TestCreatePolicy tests successful policy creation.
func TestCreatePolicy(t *testing.T) {
	contract := &PolicyContract{}
	ctx := newCtx()

	policy, err := contract.CreatePolicy(
		ctx, "policy-001", "user-001", "agent-001",
		"Star Health", "BIMA_HEALTH_BASIC",
		"200.00", "100000.00", "2026-04-05", "2027-04-05",
	)

	assert.NoError(t, err)
	assert.NotNil(t, policy)
	assert.Equal(t, "policy-001", policy.ID)
	assert.Equal(t, "active", policy.Status)
	assert.Equal(t, "user-001", policy.UserID)
}

// TestCreatePolicyDuplicate tests that creating a duplicate policy returns an error.
func TestCreatePolicyDuplicate(t *testing.T) {
	contract := &PolicyContract{}
	ctx := newCtx()

	_, err := contract.CreatePolicy(
		ctx, "policy-dup", "user-001", "agent-001",
		"Star Health", "BIMA_HEALTH_BASIC",
		"200.00", "100000.00", "2026-04-05", "2027-04-05",
	)
	assert.NoError(t, err)

	_, err = contract.CreatePolicy(
		ctx, "policy-dup", "user-001", "agent-001",
		"Star Health", "BIMA_HEALTH_BASIC",
		"200.00", "100000.00", "2026-04-05", "2027-04-05",
	)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "already exists")
}

// TestGetPolicy tests retrieving an existing policy.
func TestGetPolicy(t *testing.T) {
	contract := &PolicyContract{}
	ctx := newCtx()

	created, _ := contract.CreatePolicy(
		ctx, "policy-002", "user-002", "agent-001",
		"New India", "BIMA_ACCIDENT_PLUS",
		"100.00", "500000.00", "2026-04-05", "2027-04-05",
	)

	fetched, err := contract.GetPolicy(ctx, "policy-002")
	assert.NoError(t, err)
	assert.Equal(t, created.ID, fetched.ID)
	assert.Equal(t, "active", fetched.Status)
}

// TestGetPolicyNotFound tests that querying a non-existent policy returns an error.
func TestGetPolicyNotFound(t *testing.T) {
	contract := &PolicyContract{}
	ctx := newCtx()

	_, err := contract.GetPolicy(ctx, "non-existent")
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "does not exist")
}

// TestUpdatePolicyStatus tests valid status transition.
func TestUpdatePolicyStatus(t *testing.T) {
	contract := &PolicyContract{}
	ctx := newCtx()

	_, _ = contract.CreatePolicy(
		ctx, "policy-003", "user-003", "agent-001",
		"AIC", "BIMA_CROP_KHARIF",
		"150.00", "200000.00", "2026-04-05", "2026-10-05",
	)

	updated, err := contract.UpdatePolicyStatus(ctx, "policy-003", "lapsed")
	assert.NoError(t, err)
	assert.Equal(t, "lapsed", updated.Status)
}

// TestUpdatePolicyStatusInvalidTransition tests that an invalid transition fails.
func TestUpdatePolicyStatusInvalidTransition(t *testing.T) {
	contract := &PolicyContract{}
	ctx := newCtx()

	_, _ = contract.CreatePolicy(
		ctx, "policy-004", "user-004", "agent-001",
		"Star Health", "BIMA_HEALTH_BASIC",
		"200.00", "100000.00", "2026-04-05", "2027-04-05",
	)
	// First transition valid
	_, _ = contract.UpdatePolicyStatus(ctx, "policy-004", "cancelled")
	// Second transition from terminal state should fail
	_, err := contract.UpdatePolicyStatus(ctx, "policy-004", "active")
	assert.Error(t, err)
}

// Helper to ignore unused import
var _ = json.Marshal
