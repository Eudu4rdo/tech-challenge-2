# ToggleMaster

Projeto de microsserviços para gerenciamento e avaliação de feature flags, com autenticação, definição de flags, regras de segmentação, avaliação em tempo real e processamento assíncrono de eventos para analytics.

## Visão Geral

O sistema foi dividido em 5 serviços:

- `auth-service`: autenticação e geração/validação de chaves de API.
- `flag-service`: cadastro e consulta de feature flags.
- `targeting-service`: regras de segmentação por flag.
- `evaluation-service`: caminho principal de avaliação da flag para o cliente.
- `analytics-service`: consumo assíncrono de eventos enviados pelo `evaluation-service`.

## Arquitetura Local

Na execução local, a solução usa `docker-compose.yml` para subir:

- bancos PostgreSQL para `auth-service`, `flag-service` e `targeting-service`
- Redis para cache do `evaluation-service`
- SQS local para fila de eventos
- DynamoDB local para persistência dos eventos de analytics

## Dificuldades Encontradas

### 1. Dependências Go sem `go.sum`

O `auth-service` e o `evaluation-service` falharam no build por ausência ou inconsistência de `go.sum`.

Correção aplicada:

- geração do `go.sum`
- ajuste dos imports não utilizados
- correção da cópia de `go.sum` no Dockerfile do `evaluation-service`

### 2. Incompatibilidade Flask e Werkzeug

Os serviços Python falharam com erro de importação em `Werkzeug`, porque `Flask 2.2.2` não é compatível com `Werkzeug 3.x`.

Correção aplicada:

- fixação de `Werkzeug==2.2.3` em:
  - `flag-service`
  - `targeting-service`
  - `analytics-service`

### 3. Alpine e `psycopg2`

Os serviços Python que usam PostgreSQL falharam na instalação do `psycopg2-binary` no Alpine.

Correção aplicada:

- instalação de `build-base` e `postgresql-dev` no estágio de build
- instalação de `postgresql-libs` no estágio final

### 4. Banco PostgreSQL local sem o database esperado

O `auth-service` falhou porque o banco `auth_db` não existia no volume anterior.

Correção aplicada:

- remoção da stack com volumes
- recriação do ambiente do zero

### 5. DynamoDB local com erro de arquivo SQLite

O `dynamodb-local` falhou tentando abrir arquivo de banco no volume local.

Correção aplicada:

- uso de `-inMemory` no container do DynamoDB local

### 6. `evaluation-service` sem `SERVICE_API_KEY`

O `evaluation-service` retornava erro genérico ao avaliar a flag porque não tinha a chave de serviço usada para autenticar contra `flag-service` e `targeting-service`.

Correção aplicada:

- criação de uma chave no `auth-service`
- inclusão de `SERVICE_API_KEY` no ambiente do `evaluation-service`

## Fluxo de Teste

1. Subir a stack com Docker Compose.
2. Criar a chave de serviço para o `evaluation-service` no `auth-service`.
3. Consultar o endpoint do `evaluation-service`:

```bash
curl "http://localhost:8004/evaluate?user_id=user-123&flag_name=enable-new-dashboard"
```

4. Verificar:

- resposta da avaliação
- logs do `evaluation-service`
- mensagens chegando no SQS
- itens gravados no DynamoDB

## Próximos Passos

- finalizar os manifestos Kubernetes
- ajustar os `Deployments`, `Services`, `Ingress` e `HPA`
- documentar o fluxo de implantação na AWS
- detalhar a segunda parte do trabalho neste README

