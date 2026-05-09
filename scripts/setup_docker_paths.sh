#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

prompt_default() {
  local label="$1"
  local default="$2"
  local value
  read -r -p "${label} [${default}]: " value
  printf '%s' "${value:-$default}"
}

choose() {
  local label="$1"
  shift
  local options=("$@")
  local choice
  echo
  echo "$label"
  local i=1
  for option in "${options[@]}"; do
    echo "  ${i}. ${option}"
    i=$((i + 1))
  done
  while true; do
    read -r -p "Choose [1]: " choice
    choice="${choice:-1}"
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#options[@]} )); then
      CHOICE="$choice"
      return 0
    fi
    echo "Invalid choice."
  done
}

yaml_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "$value"
}

ensure_bind_dir() {
  local path="$1"
  [[ "$path" == /* ]] || path="$(pwd)/$path"
  mkdir -p "$path"
}

write_env_setting() {
  local key="$1"
  local value="$2"
  local tmp
  tmp="$(mktemp)"
  if [[ -f .env ]]; then
    grep -v -E "^${key}=" .env > "$tmp" || true
  fi
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  mv "$tmp" .env
}

echo "Ollama Command Deck Docker path setup"
echo "This writes docker-compose.override.yml and can recreate the web container."

app_uid="$(id -u)"
app_gid="$(id -g)"

choose "Web access" \
  "LAN access with HTTPS (recommended for phones/tablets and microphone)" \
  "Localhost only (same machine only)" \
  "Custom Docker port bind"
case "$CHOICE" in
  1)
    web_port="$(prompt_default "Web port" "8765")"
    web_port_bind="0.0.0.0:${web_port}:8765"
    ;;
  2)
    web_port="$(prompt_default "Web port" "8765")"
    web_port_bind="127.0.0.1:${web_port}:8765"
    ;;
  3)
    web_port_bind="$(prompt_default "Docker port bind" "0.0.0.0:8765:8765")"
    ;;
esac
write_env_setting "COMMAND_DECK_WEB_PORT_BIND" "$web_port_bind"

choose "Config storage (/config: generated config, API key file, session secret)" \
  "Bind mount ./config-data (recommended)" \
  "Docker named volume command-deck-config"
case "$CHOICE" in
  1)
    config_path="$(prompt_default "Config bind path" "./config-data")"
    ensure_bind_dir "$config_path"
    config_volume="$(yaml_quote "${config_path}:/config")"
    ;;
  2)
    config_volume="command-deck-config:/config"
    ;;
esac

choose "Data / agent home (/data: sessions, canvas files, users, ~/.ssh)" \
  "Bind mount current user's home (recommended for SSH and host files)" \
  "Bind mount ./data" \
  "Docker named volume command-deck-data" \
  "Custom bind path"
case "$CHOICE" in
  1)
    data_path="${HOME}"
    ensure_bind_dir "$data_path"
    data_volume="$(yaml_quote "${data_path}:/data")"
    ;;
  2)
    data_path="./data"
    ensure_bind_dir "$data_path"
    data_volume="$(yaml_quote "${data_path}:/data")"
    ;;
  3)
    data_volume="command-deck-data:/data"
    ;;
  4)
    data_path="$(prompt_default "Data bind path" "${HOME}")"
    ensure_bind_dir "$data_path"
    data_volume="$(yaml_quote "${data_path}:/data")"
    ;;
esac

choose "Workspace (/workspace: default local-command working directory)" \
  "Bind mount ./workspace" \
  "Bind mount ~/git" \
  "Custom bind path"
case "$CHOICE" in
  1)
    workspace_path="./workspace"
    ;;
  2)
    workspace_path="${HOME}/git"
    ;;
  3)
    workspace_path="$(prompt_default "Workspace bind path" "./workspace")"
    ;;
esac
ensure_bind_dir "$workspace_path"
workspace_volume="$(yaml_quote "${workspace_path}:/workspace")"

choose "SSH access" \
  "Use /data/.ssh from the data mount (best when /data is your host home)" \
  "Mount host ~/.ssh read-only, including keys" \
  "Mount only host ~/.ssh/config and known_hosts read-only" \
  "No extra SSH mount"
ssh_choice="$CHOICE"
ssh_volumes=()
ssh_agent_volume=""
ssh_agent_env=""
host_ssh_dir=""
extra_hosts=()
if [[ "$ssh_choice" == "2" ]]; then
  mkdir -p "${HOME}/.ssh"
  chmod 700 "${HOME}/.ssh" || true
  ssh_volumes+=("$(yaml_quote "${HOME}/.ssh:/data/.ssh:ro")")
  host_ssh_dir="${HOME}/.ssh"
elif [[ "$ssh_choice" == "3" ]]; then
  mkdir -p "${HOME}/.ssh"
  touch "${HOME}/.ssh/config" "${HOME}/.ssh/known_hosts"
  chmod 700 "${HOME}/.ssh" || true
  chmod 600 "${HOME}/.ssh/config" "${HOME}/.ssh/known_hosts" || true
  ssh_volumes+=("$(yaml_quote "${HOME}/.ssh/config:/data/.ssh/config:ro")")
  ssh_volumes+=("$(yaml_quote "${HOME}/.ssh/known_hosts:/data/.ssh/known_hosts:ro")")
  host_ssh_dir="${HOME}/.ssh"
elif [[ "$ssh_choice" == "1" && -n "${data_path:-}" ]]; then
  host_ssh_dir="${data_path%/}/.ssh"
fi
if [[ -n "${SSH_AUTH_SOCK:-}" && -S "${SSH_AUTH_SOCK}" && "$ssh_choice" != "4" ]]; then
  ssh_agent_volume="$(yaml_quote "${SSH_AUTH_SOCK}:/ssh-agent")"
  ssh_agent_env="/ssh-agent"
fi

if [[ "$ssh_choice" != "4" && -z "$host_ssh_dir" ]]; then
  cat <<'EOF'

Warning: /data is a Docker named volume, so option 1 does not see your host
~/.ssh files. Use SSH option 2 or bind /data to your host home if you want
existing SSH aliases.
EOF
fi

if [[ -n "$host_ssh_dir" ]]; then
  mkdir -p "$host_ssh_dir"
  touch "$host_ssh_dir/config" "$host_ssh_dir/known_hosts"
  chmod 700 "$host_ssh_dir" || true
  chmod 600 "$host_ssh_dir/config" "$host_ssh_dir/known_hosts" || true

  alias_count="$(awk 'BEGIN{c=0} /^[[:space:]]*[Hh][Oo][Ss][Tt][[:space:]]+/ { if ($2 !~ /[*?!]/) c++ } END{print c}' "$host_ssh_dir/config" 2>/dev/null || printf '0')"
  echo
  echo "SSH config the container will read:"
  echo "  Host path:      ${host_ssh_dir}/config"
  echo "  Container path: /data/.ssh/config"
  echo "  Usable aliases: ${alias_count}"

  add_alias_default="n"
  if [[ "$alias_count" == "0" ]]; then
    add_alias_default="Y"
    echo
    echo "No SSH aliases were found. Add one now so /hosts has something to show."
  fi
  if [[ "$add_alias_default" == "Y" ]]; then
    add_alias_prompt="Y/n"
  else
    add_alias_prompt="y/N"
  fi
  read -r -p "Add an SSH host alias now? [${add_alias_prompt}]: " add_alias
  add_alias="${add_alias:-$add_alias_default}"
  if [[ "$add_alias" =~ ^[Yy]$ ]]; then
    alias_name="$(prompt_default "Alias name" "server1")"
    host_name="$(prompt_default "HostName or IP" "server1.local")"
    host_user="$(prompt_default "SSH user" "${USER}")"
    default_key=""
    if [[ "$ssh_choice" == "3" ]]; then
      echo "SSH option 3 mounts config and known_hosts only. Use SSH agent or switch to option 2 if the container needs key files."
    elif [[ -f "$host_ssh_dir/id_ed25519" ]]; then
      default_key="/data/.ssh/id_ed25519"
    elif [[ -f "$host_ssh_dir/id_rsa" ]]; then
      default_key="/data/.ssh/id_rsa"
    fi
    identity_file="$(prompt_default "IdentityFile inside container (blank for SSH default)" "$default_key")"

    {
      echo
      echo "Host ${alias_name}"
      echo "  HostName ${host_name}"
      echo "  User ${host_user}"
      if [[ -n "$identity_file" ]]; then
        echo "  IdentityFile ${identity_file}"
      fi
      echo "  IdentitiesOnly yes"
    } >> "$host_ssh_dir/config"
    chmod 600 "$host_ssh_dir/config" || true

    if command -v ssh-keyscan >/dev/null 2>&1; then
      read -r -p "Add ${host_name} to known_hosts with ssh-keyscan? [y/N]: " scan_host
      if [[ "$scan_host" =~ ^[Yy]$ ]]; then
        ssh-keyscan -H "$host_name" >> "$host_ssh_dir/known_hosts" 2>/dev/null || echo "ssh-keyscan failed; SSH can still prompt/fail normally later."
        chmod 600 "$host_ssh_dir/known_hosts" || true
      fi
    fi
  fi

  if command -v getent >/dev/null 2>&1; then
    while read -r hostname; do
      [[ -n "$hostname" ]] || continue
      ip="$(getent hosts "$hostname" | awk '{print $1; exit}')"
      if [[ -n "$ip" ]]; then
        extra_hosts+=("${hostname}:${ip}")
      fi
    done < <(awk '
      BEGIN { IGNORECASE=1 }
      /^[[:space:]]*HostName[[:space:]]+/ && $2 ~ /\.local$/ { print $2 }
    ' "$host_ssh_dir/config" 2>/dev/null | sort -u)
  fi
fi

cat > docker-compose.override.yml <<YAML
# Generated by scripts/setup_docker_paths.sh.
# Re-run the script to change Docker mount paths.
services:
  web:
    build:
      args:
        APP_UID: "${app_uid}"
        APP_GID: "${app_gid}"
    volumes:
      - ${config_volume}
      - ${data_volume}
      - ${workspace_volume}
YAML

for volume in "${ssh_volumes[@]}"; do
  printf '      - %s\n' "$volume" >> docker-compose.override.yml
done
if [[ -n "$ssh_agent_volume" ]]; then
  printf '      - %s\n' "$ssh_agent_volume" >> docker-compose.override.yml
  cat >> docker-compose.override.yml <<YAML
    environment:
      SSH_AUTH_SOCK: "${ssh_agent_env}"
YAML
fi
if (( ${#extra_hosts[@]} > 0 )); then
  cat >> docker-compose.override.yml <<YAML
    extra_hosts:
YAML
  for host_entry in "${extra_hosts[@]}"; do
    printf '      - %s\n' "$(yaml_quote "$host_entry")" >> docker-compose.override.yml
  done
fi

cat <<EOF

Wrote docker-compose.override.yml
Wrote .env with Docker web port bind:
  COMMAND_DECK_WEB_PORT_BIND=${web_port_bind}

In the web setup wizard, use these in-container paths:
  SSH config path:  /data/.ssh/config
  known_hosts path: /data/.ssh/known_hosts
  work directory:   /workspace
EOF

if (( ${#extra_hosts[@]} > 0 )); then
  echo
  echo "Added Docker extra_hosts for .local SSH names:"
  for host_entry in "${extra_hosts[@]}"; do
    echo "  ${host_entry}"
  done
fi

read -r -p "Rebuild/recreate web now with ./scripts/deploy_web.sh? [Y/n]: " run_now
run_now="${run_now:-Y}"
if [[ "$run_now" =~ ^[Yy]$ ]]; then
  ./scripts/deploy_web.sh
else
  echo "Run ./scripts/deploy_web.sh when ready."
fi
