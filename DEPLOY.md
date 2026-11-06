# Deploy to VPS (web-folders)

## 1. Build & push Docker image

```bash
# From Cooking_course root
docker build -t ghcr.io/mordanov/cooking-course:latest .
docker push ghcr.io/mordanov/cooking-course:latest
```

## 2. Upload offline/ to VPS

Copy only the HTML/CSS/JS (or everything if videos aren't on Hetzner yet):

```bash
rsync -avz --exclude='*/media/' offline/ user@vps:/srv/cooking-course/offline/
# or with videos:
rsync -avz offline/ user@vps:/srv/cooking-course/offline/
```

## 3. Add to web-folders/docker-compose.yaml

```yaml
  cooking-course:
    image: ghcr.io/mordanov/cooking-course:latest
    restart: unless-stopped
    environment:
      GC_EMAIL: ${COOKING_GC_EMAIL:?COOKING_GC_EMAIL is required}
      GC_PASSWORD: ${COOKING_GC_PASSWORD:?COOKING_GC_PASSWORD is required}
      JWT_SECRET: ${COOKING_JWT_SECRET:?COOKING_JWT_SECRET is required}
    volumes:
      - /srv/cooking-course/offline:/app/offline:ro
    expose:
      - "8000"
```

## 4. Add to web-folders/sites.yaml

```yaml
  - id: cooking-course
    priority: 220
    cert_label: cooking-course
    domain:
      primary_var: COOKING_PRIMARY_DOMAIN
      server_names_var: COOKING_SERVER_NAMES
    health_path: /health
    compose_services: [cooking-course]
```

## 5. Create nginx templates in web-folders/nginx/templates/

**cooking-course-http.conf.template:**
```nginx
server {
    listen 80;
    server_name ${COOKING_SERVER_NAMES};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    location / {
        return 301 https://$host$request_uri;
    }
}
```

**cooking-course-http-redirect.conf.template** — same as http above.

**cooking-course-https.conf.template:**
```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name ${COOKING_SERVER_NAMES};

    ssl_certificate /etc/letsencrypt/live/${COOKING_PRIMARY_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${COOKING_PRIMARY_DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    client_max_body_size 0;

    location / {
        set $backend http://cooking-course:8000;
        proxy_pass $backend;
        include /etc/nginx/snippets/proxy-common.conf;
        proxy_read_timeout 60s;
    }
}
```

## 6. Add env vars to web-folders/.env

```env
COOKING_PRIMARY_DOMAIN=cooking.yourdomain.com
COOKING_SERVER_NAMES=cooking.yourdomain.com
COOKING_GC_EMAIL=your@email.com
COOKING_GC_PASSWORD=your_password
COOKING_JWT_SECRET=$(openssl rand -hex 32)
```

Also add to .env.example (without values).

## 7. Issue certificate & start

```bash
# In web-folders/ on VPS:
./issue-certificates.sh cooking-course   # if that script exists
# or via certbot manually for the domain

docker compose up -d cooking-course
```
