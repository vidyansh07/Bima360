// PolicyContract manages the insurance policy lifecycle on Hyperledger Fabric.
// Channel: bima-channel | Org: Bima360Org1MSP
//
// State transitions:
//
//	active → lapsed | claimed | cancelled
package main

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// Policy represents an insurance policy stored in Fabric world state.
type Policy struct {
	ID             string `json:"id"`
	UserID         string `json:"userId"`
	AgentID        string `json:"agentId"`
	InsurerName    string `json:"insurerName"`
	ProductCode    string `json:"productCode"`
	PremiumMonthly string `json:"premiumMonthly"`
	SumInsured     string `json:"sumInsured"`
	StartDate      string `json:"startDate"`
	EndDate        string `json:"endDate"`
	Status         string `json:"status"` // active | lapsed | claimed | cancelled
	CreatedAt      string `json:"createdAt"`
	UpdatedAt      string `json:"updatedAt"`
}

// PolicyContract implements chaincode operations for policy lifecycle.
type PolicyContract struct {
	contractapi.Contract
}

// CreatePolicy creates a new insurance policy on the ledger.
// Only callable by an authorized MSP identity (FastAPI hot wallet).
func (c *PolicyContract) CreatePolicy(
	ctx contractapi.TransactionContextInterface,
	policyID string,
	userID string,
	agentID string,
	insurerName string,
	productCode string,
	premiumMonthly string,
	sumInsured string,
	startDate string,
	endDate string,
) (*Policy, error) {
	existing, err := ctx.GetStub().GetState(policyID)
	if err != nil {
		return nil, fmt.Errorf("failed to read from world state: %w", err)
	}
	if existing != nil {
		return nil, fmt.Errorf("policy %s already exists", policyID)
	}

	now := time.Now().UTC().Format(time.RFC3339)
	policy := &Policy{
		ID:             policyID,
		UserID:         userID,
		AgentID:        agentID,
		InsurerName:    insurerName,
		ProductCode:    productCode,
		PremiumMonthly: premiumMonthly,
		SumInsured:     sumInsured,
		StartDate:      startDate,
		EndDate:        endDate,
		Status:         "active",
		CreatedAt:      now,
		UpdatedAt:      now,
	}

	policyJSON, err := json.Marshal(policy)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal policy: %w", err)
	}

	if err := ctx.GetStub().PutState(policyID, policyJSON); err != nil {
		return nil, fmt.Errorf("failed to put policy state: %w", err)
	}

	// Composite key index: userId~policyId for GetPoliciesByUser queries
	indexKey, err := ctx.GetStub().CreateCompositeKey("userId~policyId", []string{userID, policyID})
	if err != nil {
		return nil, fmt.Errorf("failed to create composite key: %w", err)
	}
	if err := ctx.GetStub().PutState(indexKey, []byte{0x00}); err != nil {
		return nil, fmt.Errorf("failed to put index: %w", err)
	}

	// Emit PolicyCreated event
	eventPayload, _ := json.Marshal(map[string]string{
		"policyId": policyID,
		"userId":   userID,
		"agentId":  agentID,
	})
	if err := ctx.GetStub().SetEvent("PolicyCreated", eventPayload); err != nil {
		return nil, fmt.Errorf("failed to emit PolicyCreated event: %w", err)
	}

	return policy, nil
}

// GetPolicy retrieves a policy by ID from the world state.
func (c *PolicyContract) GetPolicy(
	ctx contractapi.TransactionContextInterface,
	policyID string,
) (*Policy, error) {
	policyJSON, err := ctx.GetStub().GetState(policyID)
	if err != nil {
		return nil, fmt.Errorf("failed to read policy %s: %w", policyID, err)
	}
	if policyJSON == nil {
		return nil, fmt.Errorf("policy %s does not exist", policyID)
	}

	var policy Policy
	if err := json.Unmarshal(policyJSON, &policy); err != nil {
		return nil, fmt.Errorf("failed to unmarshal policy: %w", err)
	}
	return &policy, nil
}

// UpdatePolicyStatus updates the status of an existing policy.
// Valid transitions: active→lapsed, active→claimed, active→cancelled.
func (c *PolicyContract) UpdatePolicyStatus(
	ctx contractapi.TransactionContextInterface,
	policyID string,
	newStatus string,
) (*Policy, error) {
	policy, err := c.GetPolicy(ctx, policyID)
	if err != nil {
		return nil, err
	}

	validTransitions := map[string][]string{
		"active": {"lapsed", "claimed", "cancelled"},
	}
	allowed, ok := validTransitions[policy.Status]
	if !ok {
		return nil, fmt.Errorf("policy %s in terminal status %s — no transitions allowed", policyID, policy.Status)
	}

	validNew := false
	for _, s := range allowed {
		if s == newStatus {
			validNew = true
			break
		}
	}
	if !validNew {
		return nil, fmt.Errorf("invalid transition %s → %s for policy %s", policy.Status, newStatus, policyID)
	}

	policy.Status = newStatus
	policy.UpdatedAt = time.Now().UTC().Format(time.RFC3339)

	policyJSON, err := json.Marshal(policy)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal updated policy: %w", err)
	}
	if err := ctx.GetStub().PutState(policyID, policyJSON); err != nil {
		return nil, fmt.Errorf("failed to update policy state: %w", err)
	}

	eventPayload, _ := json.Marshal(map[string]string{
		"policyId":  policyID,
		"newStatus": newStatus,
	})
	if err := ctx.GetStub().SetEvent("PolicyStatusUpdated", eventPayload); err != nil {
		return nil, fmt.Errorf("failed to emit PolicyStatusUpdated event: %w", err)
	}

	return policy, nil
}

// GetPoliciesByUser returns all policies for a given userID using the composite key index.
func (c *PolicyContract) GetPoliciesByUser(
	ctx contractapi.TransactionContextInterface,
	userID string,
) ([]*Policy, error) {
	resultsIterator, err := ctx.GetStub().GetStateByPartialCompositeKey(
		"userId~policyId",
		[]string{userID},
	)
	if err != nil {
		return nil, fmt.Errorf("failed to query policies by user %s: %w", userID, err)
	}
	defer resultsIterator.Close()

	var policies []*Policy
	for resultsIterator.HasNext() {
		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, fmt.Errorf("iterator error: %w", err)
		}

		_, compositeKeyParts, err := ctx.GetStub().SplitCompositeKey(queryResponse.Key)
		if err != nil || len(compositeKeyParts) < 2 {
			continue
		}
		policyID := compositeKeyParts[1]

		policy, err := c.GetPolicy(ctx, policyID)
		if err != nil {
			continue
		}
		policies = append(policies, policy)
	}
	return policies, nil
}

func main() {
	chaincode, err := contractapi.NewChaincode(&PolicyContract{})
	if err != nil {
		panic(fmt.Sprintf("Error creating PolicyContract chaincode: %v", err))
	}
	if err := chaincode.Start(); err != nil {
		panic(fmt.Sprintf("Error starting PolicyContract chaincode: %v", err))
	}
}
