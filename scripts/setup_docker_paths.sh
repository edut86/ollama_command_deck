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

cat <<'EOF'
Ollama Command Deck — Docker setup
==================================

This sets up the app to run in Docker (a sandboxed container on your computer).
The questions below just decide which real folders on your computer the app is
allowed to see. You don't need to know Docker — the default answer (1) is the
recommended choice for each question, so you can press Enter to accept it.

Two words that come up:
  - "your computer" = the host: the normal files and folders you already have.
  - "the container"  = the sandbox the app runs inside. It only sees the folders
                       you connect here.

This writes a small settings file (docker-compose.override.yml) and can then
build and start the app for you.

EOF

app_uid="$(id -u)"
app_gid="$(id -g)"

echo "Question 1 of 5 — Who can open the web page?"
echo "  Pick LAN if you want to use it from your phone/tablet too."
choose "Web access" \
  "Anyone on my home network (phones, tablets, other PCs) — recommended" \
  "Only this computer" \
  "Let me type a custom address/port"
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

echo
echo "Question 2 of 5 — Where to keep the app's settings?"
echo "  This holds your saved config, API key, and login secret."
echo "  Option 1 keeps them in a folder you can see inside this project"
echo "  (./config-data). Option 2 hides them in Docker-managed storage."
choose "Settings storage" \
  "Keep them in this project folder: ./config-data — recommended" \
  "Let Docker store them out of sight (named volume)"
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

echo
echo "Question 3 of 5 — What files should the AI be able to read?"
echo "  This becomes the AI's home folder. Option 1 lets it use your real"
echo "  home folder (${HOME}) — your SSH setup, projects, and configs."
echo "  Choose a narrower option if you'd rather keep it walled off."
choose "AI home folder" \
  "My whole home folder: ${HOME} — recommended, enables SSH + your files" \
  "A fresh empty folder in this project: ./data" \
  "Docker-managed storage (named volume), can't see your files" \
  "Let me type a specific folder"
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

echo
echo "Question 4 of 5 — Which folder should the AI work inside?"
echo "  When it runs commands or edits files, it does so here by default."
echo "  Inside the app this folder is always called /workspace."
choose "Work folder" \
  "A fresh empty folder in this project: ./workspace — recommended" \
  "My projects folder: ${HOME}/git (pick this if you write code there)" \
  "Let me type a specific folder"
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

echo
echo "Question 5 of 5 — Let the AI connect to other machines over SSH?"
echo "  This decides whether the app can see your SSH keys (in ~/.ssh)."
echo "  Your keys are NOT copied anywhere; the app just reads them in place."
echo "  If you picked option 1 for the home folder above, option 1 here"
echo "  already works. Pick 'No' if you don't use SSH."
choose "SSH access" \
  "Use the ~/.ssh that came with my home folder — recommended" \
  "Share my ~/.ssh folder (keys included), read-only" \
  "Share only my SSH config + known_hosts (no keys), read-only" \
  "No — don't give the AI any SSH access"
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

Saved your choices. (Files written: docker-compose.override.yml and .env)

Next, the app opens in your browser and shows a setup page. If it asks for the
paths below, the values are already filled in correctly — just leave them:
  Folder the AI works in: /workspace
  SSH config path:        /data/.ssh/config
  known_hosts path:       /data/.ssh/known_hosts
EOF

if (( ${#extra_hosts[@]} > 0 )); then
  echo
  echo "Added Docker extra_hosts for .local SSH names:"
  for host_entry in "${extra_hosts[@]}"; do
    echo "  ${host_entry}"
  done
fi

echo
echo "Ready to build and start the app now? This can take a few minutes the"
echo "first time while Docker downloads and builds everything."
read -r -p "Build and start now? [Y/n]: " run_now
run_now="${run_now:-Y}"
if [[ "$run_now" =~ ^[Yy]$ ]]; then
  ./scripts/deploy_web.sh
else
  echo "No problem. When you're ready, run:  ./scripts/deploy_web.sh"
fi
