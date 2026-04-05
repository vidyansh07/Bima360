#!/usr/bin/env bash
# deploy.sh — Deploy Bima360 chaincode to Hyperledger Fabric test-network
# Run from: cd blockchain/network
# Requires: fabric-samples/test-network to be at FABRIC_SAMPLES_PATH
# Usage: ./deploy.sh [up|down|deploy-policy|deploy-claim|all]

set -euo pipefail

FABRIC_SAMPLES_PATH="${FABRIC_SAMPLES_PATH:-$HOME/fabric-samples}"
TEST_NETWORK="$FABRIC_SAMPLES_PATH/test-network"
CHAINCODE_PATH="$(cd "$(dirname "$0")/.." && pwd)"
CHANNEL="bima-channel"

check_prereqs() {
  command -v peer   >/dev/null 2>&1 || { echo "peer CLI not found. Install Fabric binaries."; exit 1; }
  command -v docker >/dev/null 2>&1 || { echo "docker not found."; exit 1; }
  if [ ! -d "$TEST_NETWORK" ]; then
    echo "fabric-samples/test-network not found at $FABRIC_SAMPLES_PATH"
    echo "Run: curl -sSL https://bit.ly/2ysbOFE | bash -s"
    exit 1
  fi
}

network_up() {
  echo "==> Starting Fabric test-network with CA..."
  cd "$TEST_NETWORK"
  ./network.sh up createChannel -c "$CHANNEL" -ca
  echo "==> Network up, channel '$CHANNEL' created"
}

network_down() {
  echo "==> Stopping Fabric test-network..."
  cd "$TEST_NETWORK"
  ./network.sh down
}

deploy_policy() {
  echo "==> Deploying PolicyContract chaincode..."
  cd "$TEST_NETWORK"
  ./network.sh deployCC \
    -ccn policy \
    -ccp "$CHAINCODE_PATH/chaincode/policy" \
    -ccl go \
    -c "$CHANNEL" \
    -ccv 1.0 \
    -ccs 1
  echo "==> PolicyContract deployed"
}

deploy_claim() {
  echo "==> Deploying ClaimContract chaincode..."
  cd "$TEST_NETWORK"
  ./network.sh deployCC \
    -ccn claim \
    -ccp "$CHAINCODE_PATH/chaincode/claim" \
    -ccl go \
    -c "$CHANNEL" \
    -ccv 1.0 \
    -ccs 1
  echo "==> ClaimContract deployed"
}

copy_wallets() {
  # Copy admin identity to backend wallets directory
  WALLET_DIR="$CHAINCODE_PATH/wallets"
  mkdir -p "$WALLET_DIR"
  echo "==> Wallet directory: $WALLET_DIR"
  echo "==> NOTE: Copy admin credentials from $TEST_NETWORK/organizations/ to $WALLET_DIR"
  echo "==> NEVER commit wallet files to git"
}

test_invoke() {
  echo "==> Testing PolicyContract.CreatePolicy..."
  peer chaincode invoke \
    -C "$CHANNEL" \
    -n policy \
    --tls \
    --cafile "$TEST_NETWORK/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem" \
    -c '{"function":"CreatePolicy","Args":["test-policy-001","user-001","agent-001","Star Health","BIMA_HEALTH_BASIC","200","100000","2026-04-05","2027-04-05"]}'
  echo "==> Test invoke complete"
}

case "${1:-help}" in
  up)            check_prereqs; network_up ;;
  down)          network_down ;;
  deploy-policy) check_prereqs; deploy_policy ;;
  deploy-claim)  check_prereqs; deploy_claim ;;
  wallets)       copy_wallets ;;
  test)          test_invoke ;;
  all)
    check_prereqs
    network_up
    sleep 5
    deploy_policy
    deploy_claim
    copy_wallets
    echo "==> Full Bima360 Fabric network deployed"
    ;;
  *)
    echo "Usage: $0 {up|down|deploy-policy|deploy-claim|wallets|test|all}"
    exit 1
    ;;
esac
