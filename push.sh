#!/usr/bin/env bash
# push ce dossier sur github
#
# 1. make an empty repo on github.com (no README, no license, no .gitignore)
# 2. make a token: GitHub > Settings > Developer settings > Personal access tokens >
#    Tokens (classic) > Generate new token (classic), scope "public_repo" (or "repo"
#    if the repo is private)
# 3. ./push.sh https://github.com/<you>/<repo>.git
#
# commits are made with your git name/email only
# the token is just used for the push, its not saved anywere
set -e
cd "$(dirname "$0")"

if ! command -v git >/dev/null; then
    echo "git is not installed (on Ubuntu: sudo apt install git)"
    exit 1
fi

url="$1"
if [ -z "$url" ]; then
    read -rp "GitHub repo URL (https://github.com/you/repo.git): " url
fi
[ -n "$url" ] || { echo "no URL given"; exit 1; }

name="$(git config user.name || true)"
email="$(git config user.email || true)"
if [ -z "$name" ]; then
    read -rp "Your name for git: " name
    git config --global user.name "$name"
fi
if [ -z "$email" ]; then
    read -rp "Your email for git (the one on your GitHub account): " email
    git config --global user.email "$email"
fi

rm -rf lib/__pycache__

if [ ! -d .git ]; then
    git init -q
    git checkout -q -b main
fi
git add -A
if git diff --cached --quiet; then
    echo "nothing new to commit"
else
    if git rev-parse -q --verify HEAD >/dev/null; then
        read -rp "Commit message: " msg
        git commit -q -m "${msg:-Update}"
    else
        git commit -q -m "First release"
    fi
fi

if git remote | grep -qx origin; then
    git remote set-url origin "$url"
else
    git remote add origin "$url"
fi
read -rsp "GitHub token (input hidden): " GH_TOKEN
echo
[ -n "$GH_TOKEN" ] || { echo "no token given"; exit 1; }
export GH_TOKEN
gpush() {
    git -c credential.helper= \
        -c credential.helper='!f() { echo username=token; echo "password=$GH_TOKEN"; }; f' \
        push "$@"
}

if ! gpush -u origin main; then
    echo
    echo "github refused the push: the repo already has commits that are not here"
    echo "(usually the README or LICENSE github makes when you create the repo)."
    read -rp "Replace what is on github with this folder? [y/N] " ok
    [ "$ok" = y ] || [ "$ok" = Y ] || { echo "nothing pushed"; exit 1; }
    gpush --force -u origin main
fi

read -rp "Tag a release version (e.g. v1.0, empty to skip): " tag
if [ -n "$tag" ]; then
    git tag -a "$tag" -m "$tag"
    gpush origin "$tag"
    echo "Tag $tag pushed. On GitHub, go to Releases > Draft a new release and pick $tag."
fi
echo "Done."
