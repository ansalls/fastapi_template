#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <domain_name>"
  echo "Example: $0 billing"
}

domain_name="${1:-}"
if [[ -z "${domain_name}" ]]; then
  usage
  exit 1
fi

if ! [[ "${domain_name}" =~ ^[a-z][a-z0-9_]*$ ]]; then
  echo "Domain name must match ^[a-z][a-z0-9_]*$"
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
domain_dir="${repo_root}/app/domains/${domain_name}"

if [[ -e "${domain_dir}" ]]; then
  echo "Domain already exists: app/domains/${domain_name}"
  exit 1
fi

mkdir -p "${domain_dir}"

cat > "${domain_dir}/__init__.py" <<EOF
"""${domain_name} domain package."""
EOF

cat > "${domain_dir}/router.py" <<EOF
from fastapi import APIRouter

router = APIRouter(prefix="/${domain_name}", tags=["${domain_name}"])


@router.get("/health", summary="${domain_name} domain health")
def ${domain_name}_health() -> dict[str, str]:
    return {"domain": "${domain_name}", "status": "ok"}
EOF

echo "Created app/domains/${domain_name}/router.py"
echo "This router is auto-discovered and mounted under /api/v1."
