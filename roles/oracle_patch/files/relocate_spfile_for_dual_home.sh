#!/usr/bin/env bash
# Relocate spfile/orapw to a durable data-dir path for dual-home switches.
# Args: gi_home db_unique_name new_oh old_oh sid oracle_base data_dir param_dir
set -euo pipefail

gi="${1:?}"
db="${2:?}"
new_oh="${3:?}"
old_oh="${4:-}"
sid="${5:?}"
base="${6:?}"
data_dir="${7:-}"
param_dir="${8:-}"
changed=0

if [ -z "$param_dir" ]; then
  if [ -n "$data_dir" ]; then
    param_dir="${data_dir}/${db}"
  elif [ -d "/${db}/d01" ]; then
    param_dir="/${db}/d01/${db}"
  else
    param_dir="${base}/parameter_files/${db}"
  fi
fi
mkdir -p "$param_dir" "${new_oh}/dbs"

cfg_spfile="$("${gi}/bin/srvctl" config database -db "$db" 2>/dev/null \
  | awk -F': ' '$1 == "Spfile" {print $2; exit}')"
cfg_pwfile="$("${gi}/bin/srvctl" config database -db "$db" 2>/dev/null \
  | awk -F': ' '$1 == "Password file" {print $2; exit}')"

src_spfile=""
for candidate in \
  "$cfg_spfile" \
  "${param_dir}/spfile${sid}.ora" \
  "${param_dir}/spfile${db}.ora" \
  "${old_oh}/dbs/spfile${sid}.ora" \
  "${old_oh}/dbs/spfile${db}.ora" \
  "${new_oh}/dbs/spfile${sid}.ora" \
  "${new_oh}/dbs/spfile${db}.ora" \
  "${param_dir}/init${sid}.ora" \
  "${old_oh}/dbs/init${sid}.ora"
do
  if [ -n "$candidate" ] && [ -f "$candidate" ]; then
    src_spfile="$candidate"
    break
  fi
done

src_pwfile=""
for candidate in \
  "$cfg_pwfile" \
  "${param_dir}/orapw${sid}" \
  "${param_dir}/orapw${db}" \
  "${old_oh}/dbs/orapw${sid}" \
  "${old_oh}/dbs/orapw${db}" \
  "${new_oh}/dbs/orapw${sid}" \
  "${new_oh}/dbs/orapw${db}"
do
  if [ -n "$candidate" ] && [ -f "$candidate" ]; then
    src_pwfile="$candidate"
    break
  fi
done

dest_spfile_durable="${param_dir}/spfile${sid}.ora"
dest_pwfile_durable="${param_dir}/orapw${sid}"
dest_pfile_durable="${param_dir}/init${sid}.ora"
dest_spfile_home="${new_oh}/dbs/spfile${sid}.ora"
dest_pwfile_home="${new_oh}/dbs/orapw${sid}"
dest_pfile_home="${new_oh}/dbs/init${sid}.ora"

copy_if_needed() {
  src="$1"
  dest="$2"
  if [ -z "$src" ] || [ ! -f "$src" ]; then
    return 1
  fi
  if [ "$src" = "$dest" ]; then
    return 0
  fi
  if [ -f "$dest" ] && cmp -s "$src" "$dest" 2>/dev/null; then
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  cp -a "$src" "$dest"
  changed=1
  return 0
}

if [ -n "$src_spfile" ]; then
  case "$src_spfile" in
    */init*.ora)
      copy_if_needed "$src_spfile" "$dest_pfile_durable" || true
      copy_if_needed "$src_spfile" "$dest_pfile_home" || true
      echo "PFILE_COPIED src=$src_spfile durable=$dest_pfile_durable home=$dest_pfile_home"
      ;;
    *)
      copy_if_needed "$src_spfile" "$dest_spfile_durable" || true
      copy_if_needed "$src_spfile" "$dest_spfile_home" || true
      "${gi}/bin/srvctl" modify database -db "$db" -spfile "$dest_spfile_durable"
      echo "SPFILE_DURABLE src=$src_spfile dest=$dest_spfile_durable mirror=$dest_spfile_home"
      ;;
  esac
else
  echo "SPFILE_MISSING old_oh=$old_oh new_oh=$new_oh param_dir=$param_dir" >&2
  exit 1
fi

if [ -n "$src_pwfile" ]; then
  copy_if_needed "$src_pwfile" "$dest_pwfile_durable" || true
  copy_if_needed "$src_pwfile" "$dest_pwfile_home" || true
  "${gi}/bin/srvctl" modify database -db "$db" -pwfile "$dest_pwfile_durable" 2>/dev/null || true
  echo "PWFILE_DURABLE src=$src_pwfile dest=$dest_pwfile_durable mirror=$dest_pwfile_home"
else
  echo "PWFILE_MISSING (continuing; local OS auth may still work)"
fi

if [ "$changed" -eq 1 ]; then
  echo CHANGED
else
  echo OK
fi
