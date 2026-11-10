#!/bin/zsh
# Stage the rater studies for the study host: each rating/studies/<id>/dist copied byte for byte to public/<id>/,
# a robots file that disallows everything, then the checks: copies identical, no project or studio word anywhere a
# rater can fetch, the kit's verify on each study, and the host's tests. Deploy only after this passes.
set -euo pipefail
cd "${0:A:h}"
BP=${BLINDPANEL_CLI:?set BLINDPANEL_CLI to the v0.2.0 checkout bin/blindpanel.mjs}
rm -rf public && mkdir public
for d in ../studies/*/(/); do
  id=${d:t}
  cp -R "$d/dist" "public/$id"
  diff -r "$d/dist" "public/$id" >/dev/null || { echo "copy of $id differs"; exit 1; }
  node "$BP" verify "$d/study.yaml" --dist "public/$id" >/dev/null || { echo "verify failed for $id"; exit 1; }
done
printf 'User-agent: *\nDisallow: /\n' > public/robots.txt
if grep -r -i -l -E "limn|nephele|studionephele|smiles|terrazzo" public api vercel.json package.json; then
  echo "a project or studio word is in the staged files"; exit 1
fi
node --test test/*.test.mjs >/dev/null
echo "staged: $(ls -d public/*/ | wc -l | tr -d ' ') studies, checks pass"
