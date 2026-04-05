// ClaimContract manages the insurance claim lifecycle on Hyperledger Fabric.
// Channel: bima-channel | Org: Bima360Org1MSP
//
// State transitions:
//
//	submitted → under_review → approved → paid
//	submitted → under_review → rejected
package main

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// Claim represents an insurance claim stored in Fabric world state.
type Claim struct {
	ID           string `json:"id"`
	PolicyID     string `json:"policyId"`
	UserID       string `json:"userId"`
	ClaimType    string `json:"claimType"`
	ClaimAmount  string `json:"claimAmount"`
	AIScore      string `json:"aiScore"`      // AI fraud score (0.0-1.0, lower = safer)
	Status       string `json:"status"`       // submitted | under_review | approved | rejected | paid
	PayoutTxHash string `json:"payoutTxHash"` // Off-chain bank transfer reference
	SubmittedAt  string `json:"submittedAt"`
	ResolvedAt   string `json:"resolvedAt"`
}

// ClaimContract implements chaincode operations for claim lifecycle.
type ClaimContract struct {
	contractapi.Contract
}

// SubmitClaim creates a new claim on the ledger.
func (c *ClaimContract) SubmitClaim(
	ctx contractapi.TransactionContextInterface,
	claimID string,
	policyID string,
	userID string,
	claimType string,
	claimAmount string,
) (*Claim, error) {
	existing, err := ctx.GetStub().GetState(claimID)
	if err != nil {
		return nil, fmt.Errorf("failed to read world state: %w", err)
	}
	if existing != nil {
		return nil, fmt.Errorf("claim %s already exists", claimID)
	}

	now := time.Now().UTC().Format(time.RFC3339)
	claim := &Claim{
		ID:          claimID,
		PolicyID:    policyID,
		UserID:      userID,
		ClaimType:   claimType,
		ClaimAmount: claimAmount,
		AIScore:     "",
		Status:      "submitted",
		SubmittedAt: now,
	}

	claimJSON, err := json.Marshal(claim)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal claim: %w", err)
	}
	if err := ctx.GetStub().PutState(claimID, claimJSON); err != nil {
		return nil, fmt.Errorf("failed to put claim state: %w", err)
	}

	// Composite key index: policyId~claimId
	indexKey, err := ctx.GetStub().CreateCompositeKey("policyId~claimId", []string{policyID, claimID})
	if err != nil {
		return nil, fmt.Errorf("failed to create composite key: %w", err)
	}
	if err := ctx.GetStub().PutState(indexKey, []byte{0x00}); err != nil {
		return nil, fmt.Errorf("failed to put index: %w", err)
	}

	eventPayload, _ := json.Marshal(map[string]string{
		"claimId":  claimID,
		"policyId": policyID,
		"userId":   userID,
	})
	if err := ctx.GetStub().SetEvent("ClaimSubmitted", eventPayload); err != nil {
		return nil, fmt.Errorf("failed to emit ClaimSubmitted event: %w", err)
	}

	return claim, nil
}

// ApproveClaim approves a submitted/under-review claim with the AI fraud score.
// Only callable by admin MSP (Bima360Org1MSP).
func (c *ClaimContract) ApproveClaim(
	ctx contractapi.TransactionContextInterface,
	claimID string,
	aiScore string,
) (*Claim, error) {
	claim, err := c.GetClaim(ctx, claimID)
	if err != nil {
		return nil, err
	}

	if claim.Status != "submitted" && claim.Status != "under_review" {
		return nil, fmt.Errorf(
			"claim %s status is %s — cannot approve",
			claimID, claim.Status,
		)
	}

	claim.AIScore = aiScore
	claim.Status = "approved"
	claim.ResolvedAt = time.Now().UTC().Format(time.RFC3339)

	claimJSON, err := json.Marshal(claim)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal claim: %w", err)
	}
	if err := ctx.GetStub().PutState(claimID, claimJSON); err != nil {
		return nil, fmt.Errorf("failed to update claim state: %w", err)
	}

	eventPayload, _ := json.Marshal(map[string]string{
		"claimId": claimID,
		"aiScore": aiScore,
	})
	if err := ctx.GetStub().SetEvent("ClaimApproved", eventPayload); err != nil {
		return nil, fmt.Errorf("failed to emit ClaimApproved event: %w", err)
	}

	return claim, nil
}

// TriggerPayout marks a claim as paid after the off-chain bank transfer completes.
// txHash is the Cashfree or bank transfer reference ID.
func (c *ClaimContract) TriggerPayout(
	ctx contractapi.TransactionContextInterface,
	claimID string,
	txHash string,
) (*Claim, error) {
	claim, err := c.GetClaim(ctx, claimID)
	if err != nil {
		return nil, err
	}

	if claim.Status != "approved" {
		return nil, fmt.Errorf(
			"claim %s must be approved before triggering payout (current: %s)",
			claimID, claim.Status,
		)
	}

	claim.PayoutTxHash = txHash
	claim.Status = "paid"
	claim.ResolvedAt = time.Now().UTC().Format(time.RFC3339)

	claimJSON, err := json.Marshal(claim)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal claim: %w", err)
	}
	if err := ctx.GetStub().PutState(claimID, claimJSON); err != nil {
		return nil, fmt.Errorf("failed to update claim to paid: %w", err)
	}

	eventPayload, _ := json.Marshal(map[string]string{
		"claimId": claimID,
		"txHash":  txHash,
	})
	if err := ctx.GetStub().SetEvent("PayoutTriggered", eventPayload); err != nil {
		return nil, fmt.Errorf("failed to emit PayoutTriggered event: %w", err)
	}

	return claim, nil
}

// GetClaim retrieves a claim by ID from the world state.
func (c *ClaimContract) GetClaim(
	ctx contractapi.TransactionContextInterface,
	claimID string,
) (*Claim, error) {
	claimJSON, err := ctx.GetStub().GetState(claimID)
	if err != nil {
		return nil, fmt.Errorf("failed to read claim %s: %w", claimID, err)
	}
	if claimJSON == nil {
		return nil, fmt.Errorf("claim %s does not exist", claimID)
	}

	var claim Claim
	if err := json.Unmarshal(claimJSON, &claim); err != nil {
		return nil, fmt.Errorf("failed to unmarshal claim: %w", err)
	}
	return &claim, nil
}

func main() {
	chaincode, err := contractapi.NewChaincode(&ClaimContract{})
	if err != nil {
		panic(fmt.Sprintf("Error creating ClaimContract chaincode: %v", err))
	}
	if err := chaincode.Start(); err != nil {
		panic(fmt.Sprintf("Error starting ClaimContract chaincode: %v", err))
	}
}
