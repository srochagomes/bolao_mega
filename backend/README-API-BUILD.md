# Build da API - Documentação

Este diretório contém os arquivos necessários para fazer o build apenas da API (backend).

## Arquivos de Build

- `Dockerfile` - Dockerfile para construir a imagem da API
- `build-api.sh` - Script para fazer o build da imagem Docker
- `docker-compose.yml` - Arquivo docker-compose para facilitar o deploy
- `.dockerignore` - Arquivos a serem ignorados no build

## Como Fazer o Build

### Opção 1: Usando o Script

```bash
cd backend
./build-api.sh
```

### Opção 2: Usando Docker diretamente

```bash
cd backend
docker build -t bolao-loteria-api:latest .
```

### Opção 3: Usando Docker Compose

```bash
cd backend
docker-compose build
```

## Como Executar

### Opção 1: Docker Run

```bash
docker run -p 8000:8000 \
  -v $(pwd)/storage:/app/storage \
  bolao-loteria-api:latest
```

### Opção 2: Docker Compose

```bash
cd backend
docker-compose up
```

### Opção 3: Docker Compose em Background

```bash
cd backend
docker-compose up -d
```

## Verificar se está funcionando

Após iniciar o container, acesse:

- API: http://localhost:8000
- Documentação: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

## Variáveis de Ambiente

Você pode configurar variáveis de ambiente através do docker-compose.yml ou passando `-e` no docker run:

```bash
docker run -p 8000:8000 \
  -e PYTHONUNBUFFERED=1 \
  -v $(pwd)/storage:/app/storage \
  bolao-loteria-api:latest
```

## Volumes

O diretório `storage` é montado como volume para persistir:
- Arquivos Excel gerados (`storage/excel_files/`)
- Metadados e contadores (`storage/metadata/`)

## Logs

Para ver os logs do container:

```bash
docker logs bolao-loteria-api
```

Ou com docker-compose:

```bash
docker-compose logs -f
```

## Parar o Container

```bash
docker stop bolao-loteria-api
```

Ou com docker-compose:

```bash
docker-compose down
```

