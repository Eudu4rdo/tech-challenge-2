# ToggleMaster
O ToggleMaster é uma aplicação baseada em microsserviços para gerenciamento e avaliação de feature flags. A solução contempla autenticação, cadastro de flags, definição de regras de segmentação, avaliação em tempo real e processamento assíncrono de eventos para analytics.

## Visão Geral

O projeto foi dividido em cinco serviços, cada um com uma responsabilidade bem definida:

- `auth-service`: autenticação e geração/validação de chaves de API.
- `flag-service`: cadastro e consulta de feature flags.
- `targeting-service`: regras de segmentação por flag.
- `evaluation-service`: avaliação das flags consumidas pelos clientes.
- `analytics-service`: consumo assíncrono de eventos enviados pelo `evaluation-service`.

Cada serviço possui seu próprio `Dockerfile`, respeitando as diferenças de stack, dependências e requisitos de execução.

## Arquitetura

Fluxo principal:

1. O cliente autentica e consome os endpoints expostos pelos serviços.
2. O `auth-service` valida a autenticação e emite a chave necessária para acesso aos demais serviços.
3. `flag-service` mantém as feature flags.
4. `targeting-service` guarda as regras de segmentação associadas às flags.
5. `evaluation-service` consulta o cache e os serviços internos para decidir o resultado da flag.
6. `analytics-service` consome os eventos publicados na fila e grava os dados no DynamoDB.

### Desenho da arquitetura

![Diagrama](./diagrama.png)

### Provisionamento de recursos

Além dos serviços da aplicação, foi necessário provisionar recursos na AWS para persistência, cache e comunicação assíncrona:

- `RDS`: três bases relacionais PostgreSQL, utilizadas para persistência dos dados transacionais da aplicação.
- `ElastiCache Redis`: cache em memória utilizado para otimizar o tempo de resposta na avaliação das flags.
- `DynamoDB`: banco não relacional utilizado para armazenar dados analíticos sem necessidade de estrutura relacional rígida.
- `SQS`: fila Standard utilizada para publicar eventos que serão consumidos de forma assíncrona.

#### Diferença entre os três tipos de armazenamento

Cada serviço possui uma necessidade específica de armazenamento. Para os serviços responsáveis pelo controle dos dados da aplicação (`auth-service`, `flag-service` e `targeting-service`), foi utilizado PostgreSQL, pois o modelo relacional garante maior integridade e consistência.

No `evaluation-service`, a prioridade é o tempo de resposta. Por isso, foi utilizado Redis como cache em memória, reduzindo a necessidade de consultas repetidas aos serviços internos. Já o `analytics-service` utiliza DynamoDB, uma opção adequada para armazenar eventos analíticos que não exigem uma estrutura relacional rígida.

## Teste local

O ambiente local foi montado com `docker-compose.yml`, responsável por provisionar os recursos necessários e construir os containers com base no `Dockerfile` de cada serviço.

### O que sobe localmente

- Bancos PostgreSQL para `auth-service`, `flag-service` e `targeting-service`.
- Redis para cache do `evaluation-service`.
- SQS local para fila de eventos.
- DynamoDB local para persistência dos eventos de analytics.

No ambiente local, também foi criado um arquivo `.env` para configurar a variável `SERVICE_API_KEY`, essencial para a comunicação autenticada entre os serviços.

## Provisionamento no Kubernetes

A abordagem escolhida para este projeto foi utilizar um único cluster e um único namespace. Essa decisão considera o escopo do trabalho e evita a complexidade adicional que seria gerada pela separação de namespaces por microsserviço.

Mesmo com essa simplificação, o isolamento operacional necessário é mantido, pois cada microsserviço possui seus próprios manifestos de configuração e provisionamento. Dentro do namespace, os recursos continuam separados por nome:

- `auth-service`
- `flag-service`
- `targeting-service`
- `evaluation-service`
- `analytics-service`

Outra decisão tomada para simplificar a entrega foi a adoção de um monorepo. Assim, todos os serviços ficam no mesmo repositório Git, facilitando a apresentação e a navegação pelo projeto. Apesar disso, cada serviço mantém suas particularidades de implementação, dependências e execução.

### Orquestração e implantação com manifestos

O ponto central do desafio foi a construção dos manifestos Kubernetes, responsáveis por configurar e provisionar os recursos no cluster. Eles foram criados com base nas boas práticas do Kubernetes e na documentação oficial, buscando garantir uma implantação organizada e segura.

Alguns manifestos são comuns a todo o cluster, enquanto outros são específicos de cada serviço. Todos os arquivos utilizados pela aplicação estão disponíveis na pasta [k8s](./k8s/).

## Manifestos Kubernetes

- **Namespace**: cria o namespace onde todos os recursos da aplicação são provisionados, evitando conflito de nomes com outros recursos do cluster.
- **ConfigMap**: armazena configurações que podem ser alteradas sem a necessidade de reconstruir a imagem do container.
- **Secret**: armazena informações sensíveis, como senhas e chaves de API. Os valores são declarados em Base64. Para fins de demonstração, os manifestos de secrets foram versionados no repositório; em um ambiente de produção, eles não devem ser mantidos dessa forma.
- **Deployment**: gerencia a criação, atualização e disponibilidade dos pods de cada serviço.
- **Job**: executa tarefas pontuais ou recorrentes. Neste projeto, foi utilizado para criar as tabelas necessárias nos bancos relacionais usados por `auth-service`, `flag-service` e `targeting-service`.
- **Service**: expõe os pods internamente no cluster e direciona o tráfego para as instâncias corretas.
- **Ingress**: gerencia o acesso externo aos serviços. Neste projeto, foi utilizado para criar um endpoint único e aplicar as regras de roteamento para os diferentes serviços.


============================================================================================== 

REFAZER

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


# DIFICULDADES NA NUVEM
- Como usamos a conta do Academy em alguns momentos tivemos problemas de várias conexões simultaneas
- Tentamos implementar na VPC padrão da conta e tivemos erros
- Problemas pois esquecemos de colocar o Redis no Security Group
- Precisamos ajustar o Ingress para fazer rewrite do path pois estavamos recebendo 404 (as rotas de health precisam vir com o prefixo da regra e as outras não)
=============================
### Uso de IA

### Autores

| Nome | RM | Discord | E-mail |
| --- | --- | --- | --- |
|  Allison Martins Orsini | rm375470 | Alisson Martins Orsini - rm375470 | alisson_mo@hotmail.com |
|  Diogo Soares da Silva |  |  |  |
|  Eduardo Garcia Barbara | rm374946 | Eduardo Garcia - rm374946 | eg47202@gmail.com |
|  Eduardo Luiz Fonseca |  |  |  |

### Link do certificado do Google Skills
[Google Skils](https://www.skills.google/public_profiles/4f177b68-0d79-4fde-b512-587be7c62bed)
