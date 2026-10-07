# The site used to be built on a laptop and committed as public/, which is how
# the Commento migration ended up living only in an uncommitted submodule edit.
# Building here instead means the image is reproducible from the source alone.

# Extended Hugo: the theme compiles SCSS. Pinned so a Hugo release cannot
# silently change the rendered output -- renovate bumps it deliberately.
FROM hugomods/hugo:exts-0.154.5 AS build
WORKDIR /src
COPY . .
# No --minify on purpose: it would change every page relative to what the site
# serves today, hiding real diffs behind whitespace churn.
RUN hugo --destination /public

FROM caddy:2.11-alpine
EXPOSE 5000
WORKDIR /app/html
COPY --from=build /public /app/html
ENTRYPOINT ["caddy", "file-server", "--listen", ":5000"]
