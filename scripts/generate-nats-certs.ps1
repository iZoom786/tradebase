# Generate self-signed TLS certificates for NATS (Development only)
# WARNING: These certificates are for development purposes only
# For production, use certificates from a trusted CA

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CertsDir = Join-Path $ScriptDir "..\infrastructure\nats\certs"
$CertValidDays = 3650  # 10 years

Write-Host "=== NATS TLS Certificate Generator (Development) ===" -ForegroundColor Green
Write-Host "WARNING: These are self-signed certificates for development only!" -ForegroundColor Yellow
Write-Host ""

# Create certs directory if it doesn't exist
if (-not (Test-Path $CertsDir)) {
    New-Item -ItemType Directory -Path $CertsDir -Force | Out-Null
}
Set-Location $CertsDir

# Configuration file path
$ConfigFile = "cert.cnf"

# Create OpenSSL configuration file
$ConfigContent = @"
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

[v3_client]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = clientAuth

[alt_names]
DNS.1 = localhost
DNS.2 = nats
DNS.3 = *.tradebase.com
DNS.4 = tradebase.com
IP.1 = 127.0.0.1
IP.2 = ::1
"@

Set-Content -Path $ConfigFile -Value $ConfigContent

# Check if OpenSSL is available
$OpenSslExists = $false
try {
    $null = Get-Command openssl -ErrorAction Stop
    $OpenSslExists = $true
} catch {
    Write-Host "OpenSSL not found in PATH. Trying to use Windows certificate generation..." -ForegroundColor Yellow
}

if ($OpenSslExists) {
    Write-Host "Using OpenSSL for certificate generation..." -ForegroundColor Green

    # Step 1: Generate CA certificate and private key
    Write-Host "Step 1: Generating CA certificate..." -ForegroundColor Green
    openssl genrsa -out ca.key 4096 2>$null
    openssl req -new -x509 -days $CertValidDays -key ca.key -out ca.crt -config $ConfigFile -extensions v3_ca

    # Step 2: Generate server private key
    Write-Host "Step 2: Generating server private key..." -ForegroundColor Green
    openssl genrsa -out server.key 2048 2>$null

    # Step 3: Generate server certificate signing request
    Write-Host "Step 3: Generating server CSR..." -ForegroundColor Green
    openssl req -new -key server.key -out server.csr -config $ConfigFile -subj "/C=US/ST=CA/L=San Francisco/O=Tradebase/OU=Development/CN=nats"

    # Step 4: Sign server certificate with CA
    Write-Host "Step 4: Signing server certificate with CA..." -ForegroundColor Green
    openssl x509 -req -days $CertValidDays -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial `
        -out server.crt -config $ConfigFile -extensions v3_server

    # Step 5: Generate client private key
    Write-Host "Step 5: Generating client private key..." -ForegroundColor Green
    openssl genrsa -out client.key 2048 2>$null

    # Step 6: Generate client certificate
    Write-Host "Step 6: Generating client certificate..." -ForegroundColor Green
    openssl req -new -key client.key -out client.csr -config $ConfigFile -subj "/C=US/ST=CA/L=San Francisco/O=Tradebase/OU=Client/CN=client"
    openssl x509 -req -days $CertValidDays -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial `
        -out client.crt -config $ConfigFile -extensions v3_client

    # Clean up temporary files
    Remove-Item -Path server.csr, client.csr, ca.srl, $ConfigFile -Force -ErrorAction SilentlyContinue

} else {
    Write-Host "Generating certificates using PowerShell..." -ForegroundColor Green

    # Use PowerShell's New-SelfSignedCertificate cmdlet (Windows 8+)
    # Step 1: Generate CA certificate
    Write-Host "Step 1: Generating CA certificate..." -ForegroundColor Green
    $CaCert = New-SelfSignedCertificate `
        -Type Custom `
        -Subject "CN=Tradebase CA, O=Tradebase, OU=Development, C=US, ST=CA, L=San Francisco" `
        -KeyUsage CertSign, CRLSign `
        -CertStoreLocation "Cert:\LocalMachine\My" `
        -KeyLength 4096 `
        -NotAfter (Get-Date).AddYears(10)

    # Export CA certificate and key
    $CaCertBytes = $CaCert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
    [System.IO.File]::WriteAllBytes((Join-Path $CertsDir "ca.crt"), $CaCertBytes)

    # Step 2: Generate server certificate
    Write-Host "Step 2: Generating server certificate..." -ForegroundColor Green
    $ServerCert = New-SelfSignedCertificate `
        -Type Custom `
        -Subject "CN=nats, O=Tradebase, OU=Development, C=US, ST=CA, L=San Francisco" `
        -KeyUsage DigitalSignature, KeyEncipherment `
        -CertStoreLocation "Cert:\LocalMachine\My" `
        -Signer $CaCert `
        -KeyLength 2048 `
        -NotAfter (Get-Date).AddYears(10) `
        -TextExtension @("2.5.29.17={text}DNS=localhost&DNS=nats&DNS=*.tradebase.com&DNS=tradebase.com&IP=127.0.0.1")

    # Export server certificate
    $ServerCertBytes = $ServerCert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
    [System.IO.File]::WriteAllBytes((Join-Path $CertsDir "server.crt"), $ServerCertBytes)

    # Export server private key (with password)
    $ServerCertPassword = ConvertTo-SecureString -String "tradebase" -Force -AsPlainText
    Export-PfxCertificate -Cert $ServerCert -FilePath (Join-Path $CertsDir "server.pfx") -Password $ServerCertPassword

    # Step 3: Generate client certificate
    Write-Host "Step 3: Generating client certificate..." -ForegroundColor Green
    $ClientCert = New-SelfSignedCertificate `
        -Type Custom `
        -Subject "CN=client, O=Tradebase, OU=Client, C=US, ST=CA, L=San Francisco" `
        -KeyUsage DigitalSignature, KeyEncipherment `
        -CertStoreLocation "Cert:\LocalMachine\My" `
        -Signer $CaCert `
        -KeyLength 2048 `
        -NotAfter (Get-Date).AddYears(10)

    # Export client certificate
    $ClientCertBytes = $ClientCert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
    [System.IO.File]::WriteAllBytes((Join-Path $CertsDir "client.crt"), $ClientCertBytes)

    # Export client private key
    Export-PfxCertificate -Cert $ClientCert -FilePath (Join-Path $CertsDir "client.pfx") -Password $ServerCertPassword

    Write-Host "Note: Certificates generated using PowerShell (PFX format)" -ForegroundColor Yellow
    Write-Host "  - server.pfx : Server certificate with private key (password: tradebase)" -ForegroundColor Yellow
    Write-Host "  - client.pfx : Client certificate with private key (password: tradebase)" -ForegroundColor Yellow
}

# Set file permissions
if ($OpenSslExists) {
    Write-Host "Step 7: Setting file permissions..." -ForegroundColor Green
    # On Windows, we use icacls instead of chmod
    icacls .\ca.crt /inheritance:r /grant:r "$($env:USERNAME):(R)" 2>$null
    icacls .\server.crt /inheritance:r /grant:r "$($env:USERNAME):(R)" 2>$null
    icacls .\client.crt /inheritance:r /grant:r "$($env:USERNAME):(R)" 2>$null
}

Write-Host ""
Write-Host "=== Certificate generation complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Generated files:"
Write-Host "  - ca.crt      : CA certificate (trust this in your browser/system)"
Write-Host "  - server.crt  : Server certificate"
Write-Host "  - client.crt  : Client certificate (for client auth)"
Write-Host ""
Write-Host "To trust these certificates on Windows:" -ForegroundColor Yellow
Write-Host "  1. Right-click on ca.crt"
Write-Host "  2. Select 'Install Certificate'"
Write-Host "  3. Select 'Trusted Root Certification Authorities'"
Write-Host "  4. Complete the wizard"
Write-Host ""
Write-Host "Certificates are located in: $CertsDir" -ForegroundColor Green
