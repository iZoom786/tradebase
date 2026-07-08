#!/bin/bash
# Generate self-signed TLS certificates for NATS (Development only)
# WARNING: These certificates are for development purposes only
# For production, use certificates from a trusted CA

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERTS_DIR="${SCRIPT_DIR}/../infrastructure/nats/certs"
CERT_VALID_DAYS=3650  # 10 years

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== NATS TLS Certificate Generator (Development) ===${NC}"
echo -e "${YELLOW}WARNING: These are self-signed certificates for development only!${NC}"
echo ""

# Create certs directory if it doesn't exist
mkdir -p "${CERTS_DIR}"
cd "${CERTS_DIR}"

# Configuration for certificate generation
CONFIG_FILE="cert.cnf"

cat > "$CONFIG_FILE" <<EOF
[req]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_ca

[dn]
C = US
ST = CA
L = San Francisco
O = Tradebase
OU = Development
CN = Tradebase NATS

[v3_ca]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical,CA:true
keyUsage = critical,digitalSignature,keyCertSign,cRLSign

[v3_server]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth,clientAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = nats
DNS.3 = *.tradebase.com
DNS.4 = tradebase.com
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

# Step 1: Generate CA certificate and private key
echo -e "${GREEN}Step 1: Generating CA certificate...${NC}"
openssl genrsa -out ca.key 4096 2>/dev/null
openssl req -new -x509 -days $CERT_VALID_DAYS -key ca.key -out ca.crt -config "$CONFIG_FILE" -extensions v3_ca

# Step 2: Generate server private key
echo -e "${GREEN}Step 2: Generating server private key...${NC}"
openssl genrsa -out server.key 2048 2>/dev/null

# Step 3: Generate server certificate signing request
echo -e "${GREEN}Step 3: Generating server CSR...${NC}"
openssl req -new -key server.key -out server.csr -config "$CONFIG_FILE" -subj "/C=US/ST=CA/L=San Francisco/O=Tradebase/OU=Development/CN=nats"

# Step 4: Sign server certificate with CA
echo -e "${GREEN}Step 4: Signing server certificate with CA...${NC}"
openssl x509 -req -days $CERT_VALID_DAYS -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -config "$CONFIG_FILE" -extensions v3_client

# Step 5: Generate client private key (for client authentication if needed)
echo -e "${GREEN}Step 5: Generating client private key...${NC}"
openssl genrsa -out client.key 2048 2>/dev/null

# Step 6: Generate client certificate
echo -e "${GREEN}Step 6: Generating client certificate...${NC}"
openssl req -new -key client.key -out client.csr -config "$CONFIG_FILE" -subj "/C=US/ST=CA/L=San Francisco/O=Tradebase/OU=Client/CN=client"
openssl x509 -req -days $CERT_VALID_DAYS -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out client.crt -config "$CONFIG_FILE" -extensions v3_client

# Step 7: Set appropriate permissions
echo -e "${GREEN}Step 7: Setting file permissions...${NC}"
chmod 644 ca.crt server.crt client.crt
chmod 600 ca.key server.key client.key

# Step 8: Generate PKCS#12 format for Windows clients (optional)
echo -e "${GREEN}Step 8: Generating PKCS#12 bundle...${NC}"
openssl pkcs12 -export -out client.p12 -inkey client.key -in client.crt -certfile ca.crt \
    -passout pass:tradebase

# Clean up temporary files
rm -f server.csr client.csr ca.srl "$CONFIG_FILE"

echo ""
echo -e "${GREEN}=== Certificate generation complete! ===${NC}"
echo ""
echo "Generated files:"
echo "  - ca.crt      : CA certificate (trust this in your browser/system)"
echo "  - ca.key      : CA private key (KEEP SECRET!)"
echo "  - server.crt  : Server certificate"
echo "  - server.key  : Server private key (KEEP SECRET!)"
echo "  - client.crt  : Client certificate (for client auth)"
echo "  - client.key  : Client private key (KEEP SECRET!)"
echo "  - client.p12  : Client certificate in PKCS#12 format"
echo ""
echo -e "${YELLOW}To trust these certificates on your system:${NC}"
echo "  macOS:       sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ca.crt"
echo "  Windows:     Import ca.crt into 'Trusted Root Certification Authorities'"
echo "  Linux:       sudo cp ca.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates"
echo ""
echo -e "${GREEN}Certificates are located in: ${CERTS_DIR}${NC}"
