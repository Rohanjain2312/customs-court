# Handoff

Things Rohan may need to do, plus the state of the environment. Updated as work goes on.

## Environment check (2026-09-28)

| Item | State |
|---|---|
| `ANTHROPIC_API_KEY` | Present in `.env` (copied from `loan-servicing-agent/.env` with Rohan's approval) |
| `OPENAI_API_KEY` | Present in `.env` (same source, same approval) |
| `HF_TOKEN` | Present at `~/.cache/huggingface/token` (account rohanjain2312). Not copied into `.env`. |
| `gh auth status` | Logged in as Rohanjain2312, scopes repo and workflow |
| GitHub repo | https://github.com/Rohanjain2312/customs-court, private, remote `origin`, branch `main` |
| uv | 0.x at `~/.local/bin/uv`, Python 3.12 |
| Node | v24.21.0 LTS, installed to `~/.local/opt` from nodejs.org (checksum verified) |
| Terraform | 1.16.4, installed to `~/.local/bin` from releases.hashicorp.com (checksum verified) |
| Docker | Docker CLI 29.8.1 plus Colima 0.10.3 and Lima 2.2.0 (user-local, no admin). Colima VM: 4 CPU, 6 GB RAM, 40 GB disk, vz, arm64 |
| Homebrew | Not installed. Not needed. |

To use the tools in a new shell: `export PATH=~/.local/bin:~/.local/opt/lima/bin:$PATH`, then `colima start` if Docker is needed.

## Open items for Rohan

(Filled in as the project goes.)
