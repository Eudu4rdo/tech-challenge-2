# ToggleMaster

Projeto de microsserviços para gerenciamento e avaliação de feature flags, com autenticação, definição de flags, regras de segmentação, avaliação em tempo real e processamento assíncrono de eventos para analytics.

## Visão Geral

O ToggleMaster foi dividido em 5 serviços, cada um com responsabilidade bem definida:

- `auth-service`: autenticação e geração/validação de chaves de API.
- `flag-service`: cadastro e consulta de feature flags.
- `targeting-service`: regras de segmentação por flag.
- `evaluation-service`: caminho principal de avaliação da flag para o cliente.
- `analytics-service`: consumo assíncrono de eventos enviados pelo `evaluation-service`.

### Objetivo da solução

A ideia é permitir que uma flag seja criada, avaliada e monitorada de forma desacoplada. O caminho de leitura precisa responder rápido para o cliente, enquanto o analytics pode processar eventos em segundo plano.

### Papel dos data stores

- `RDS`: persiste os dados transacionais dos serviços `auth-service`, `flag-service` e `targeting-service`.
- `ElastiCache`: acelera a leitura de decisões de avaliação no `evaluation-service`.
- `DynamoDB`: armazena os eventos assíncronos de analytics.

### Estratégia de cluster e namespace

Para este projeto, a abordagem recomendada é usar **um único cluster** e **um namespace por ambiente**, em vez de um namespace para cada microsserviço.

Essa escolha reduz a complexidade operacional e mantém o isolamento necessário entre os ambientes. Como os cinco serviços fazem parte da mesma aplicação e compartilham o mesmo ciclo de entrega, separar por microsserviço traria mais custo do que benefício.

Dentro do namespace, os recursos continuam separados por nome:
- `auth-service`
- `flag-service`
- `targeting-service`
- `evaluation-service`
- `analytics-service`

## Arquitetura

Fluxo principal:

1. O cliente autentica e consome os endpoints expostos pelos serviços.
2. `auth-service` valida a autenticação e emite a base para acesso aos demais serviços.
3. `flag-service` mantém as feature flags.
4. `targeting-service` guarda as regras de segmentação associadas às flags.
5. `evaluation-service` consulta cache e serviços internos para decidir o resultado da flag.
6. `analytics-service` consome eventos da fila e grava os dados no DynamoDB.

### Desenho da arquitetura

[Diagrama](./diagrama.png)

## Teste Local

O ambiente local foi montado com `docker-compose.yml`, que sobe os serviços da aplicação e as dependências necessárias para a execução.

### O que sobe localmente

- bancos PostgreSQL para `auth-service`, `flag-service` e `targeting-service`
- Redis para cache do `evaluation-service`
- SQS local para fila de eventos
- DynamoDB local para persistência dos eventos de analytics

### Validação do fluxo

1. Subir a stack local com Docker Compose.
2. Criar a chave de serviço para o `evaluation-service` no `auth-service`.
3. Chamar o endpoint de avaliação:

```bash
curl "http://localhost:8004/evaluate?user_id=user-123&flag_name=enable-new-dashboard"
```

4. Verificar:

- resposta da avaliação
- logs do `evaluation-service`
- mensagens chegando no SQS
- itens gravados no DynamoDB

## Resumo dos Desafios no Ambiente Local

Os principais problemas encontrados para rodar localmente foram os seguintes:

### Dependências Go sem `go.sum`

Os serviços Go falharam no build por ausência ou inconsistências no `go.sum`.

O que foi feito:

- geração do `go.sum`
- ajuste de imports não utilizados
- correção da cópia de `go.sum` no Dockerfile do `evaluation-service`

### Incompatibilidade entre Flask e Werkzeug

Os serviços Python falharam com erro de importação no `Werkzeug`, porque `Flask 2.2.2` não era compatível com `Werkzeug 3.x`.

O que foi feito:

- fixação de `Werkzeug==2.2.3` em:
  - `flag-service`
  - `targeting-service`
  - `analytics-service`

### Alpine e `psycopg2`

Os serviços Python que usam PostgreSQL falharam na instalação do `psycopg2-binary` no Alpine.

O que foi feito:

- instalação de `build-base` e `postgresql-dev` no estágio de build
- instalação de `postgresql-libs` no estágio final

### Banco PostgreSQL local sem o banco esperado

O `auth-service` falhou porque o banco `auth_db` não existia no volume anterior.

O que foi feito:

- remoção da stack com volumes
- recriação do ambiente do zero

### DynamoDB local com erro de arquivo SQLite

O `dynamodb-local` falhou tentando abrir arquivo de banco no volume local.

O que foi feito:

- uso de `-inMemory` no container do DynamoDB local

### `evaluation-service` sem `SERVICE_API_KEY`

O `evaluation-service` retornava erro genérico ao avaliar a flag porque não tinha a chave de serviço usada para autenticar contra `flag-service` e `targeting-service`.

O que foi feito:

- criação de uma chave no `auth-service`
- inclusão de `SERVICE_API_KEY` no ambiente do `evaluation-service`

## Tópicos para a Próxima Versão

### Provisionamento dos recursos em nuvem

- RDS
- ElastiCache
- DynamoDB
- SQS
- ECR
- IAM / LabRole
- guia rapido: [provisionamento-recursos-aws.md](./provisionamento-recursos-aws.md)

### Configuração do cluster

- criação e organização do namespace
- acessos e permissões
- integração do cluster com os recursos da AWS

### Orquestração e implantação com manifestos

- `Namespace`
- `ConfigMap`
- `Secret`
- `Deployment`
- `Service`
- `Ingress`

### Configuração e escalabilidade

- estratégia de escalabilidade do `analytics-service`
- HPA por CPU ou KEDA por fila
- justificativa da escolha


# DIFICULDADES NO SERVIDOR
- Tentamos implementar na VPC padrão da conta e tivemos erros
- Problemas pois esquecemos de colocar o Redis no Security Group
- Precisamos ajustar o Ingress para fazer rewrite do path pois estavamos recebendo 404 (as rotas de health precisam vir com o prefixo da regra e as outras não)