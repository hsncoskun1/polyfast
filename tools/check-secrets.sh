#!/bin/bash
# Pre-commit secret leak checker
# Run: bash tools/check-secrets.sh

echo "Checking for secret leaks in staged files..."

# Patterns to detect — add new credential patterns here
PATTERNS=(
    "762cd4c8"
    "019d57d9"
    "E5be1b13738d"
    "-4_hg6vy"
    "19b90b9c"
    "0xE5be1b"
    "PRIVATE_KEY=.*[a-f0-9]{64}"
    "API_KEY=.*[a-f0-9-]{36}"
    "SECRET=.*[A-Za-z0-9+/=]{20,}"
    "PASSPHRASE=.*[a-f0-9]{64}"
)

FOUND=0
for pattern in "${PATTERNS[@]}"; do
    result=$(git diff --cached --diff-filter=ACMR -U0 | grep -iE "$pattern" 2>/dev/null)
    if [ -n "$result" ]; then
        echo "BLOCKED: Potential secret found matching pattern: $pattern"
        echo "$result" | head -3
        FOUND=1
    fi
done

if [ $FOUND -eq 1 ]; then
    echo ""
    echo "COMMIT BLOCKED: Secret leak detected!"
    echo "Remove sensitive values before committing."
    exit 1
fi

echo "OK: No secrets detected."
exit 0
