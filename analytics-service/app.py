import os
import sys
import threading
import json
import uuid
import time
import logging
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from flask import Flask, jsonify
from dotenv import load_dotenv

# Configura o logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Carrega .env para desenvolvimento local
load_dotenv()

# --- Configuração ---
AWS_REGION = os.getenv("AWS_REGION")
SQS_QUEUE_URL = os.getenv("AWS_SQS_URL")
DYNAMODB_TABLE_NAME = os.getenv("AWS_DYNAMODB_TABLE")
AWS_SQS_ENDPOINT_URL = os.getenv("AWS_SQS_ENDPOINT_URL")
AWS_DYNAMODB_ENDPOINT_URL = os.getenv("AWS_DYNAMODB_ENDPOINT_URL")

if not all([AWS_REGION, SQS_QUEUE_URL, DYNAMODB_TABLE_NAME]):
    log.critical("Erro: AWS_REGION, AWS_SQS_URL, e AWS_DYNAMODB_TABLE devem ser definidos.")
    sys.exit(1)

# --- Clientes Boto3 ---
# Criamos a sessão uma vez
try:
    session = boto3.Session(region_name=AWS_REGION)
    sqs_client = session.client("sqs", endpoint_url=AWS_SQS_ENDPOINT_URL)
    dynamodb_client = session.client("dynamodb", endpoint_url=AWS_DYNAMODB_ENDPOINT_URL)
    log.info(f"Clientes Boto3 inicializados na região {AWS_REGION}")
except NoCredentialsError:
    log.critical("Credenciais da AWS não encontradas. Verifique seu ambiente.")
    sys.exit(1)
except Exception as e:
    log.critical(f"Erro ao inicializar o Boto3: {e}")
    sys.exit(1)


def ensure_dynamodb_table():
    """Cria a tabela do DynamoDB Local quando ela ainda não existir."""
    if not AWS_DYNAMODB_ENDPOINT_URL:
        return

    for attempt in range(1, 31):
        try:
            dynamodb_client.describe_table(TableName=DYNAMODB_TABLE_NAME)
            log.info(f"Tabela DynamoDB local '{DYNAMODB_TABLE_NAME}' já existe.")
            return
        except Exception as e:
            if isinstance(e, ClientError):
                error_code = e.response.get("Error", {}).get("Code")
                if error_code != "ResourceNotFoundException":
                    log.warning("Aguardando DynamoDB local ficar pronto: %s", e)
                    time.sleep(1)
                    continue
            else:
                log.warning("Aguardando DynamoDB local ficar pronto: %s", e)
                time.sleep(1)
                continue

        try:
            dynamodb_client.create_table(
                TableName=DYNAMODB_TABLE_NAME,
                AttributeDefinitions=[
                    {"AttributeName": "event_id", "AttributeType": "S"},
                ],
                KeySchema=[
                    {"AttributeName": "event_id", "KeyType": "HASH"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            log.info(f"Tabela DynamoDB local '{DYNAMODB_TABLE_NAME}' criada.")
        except Exception as e:
            if isinstance(e, ClientError):
                error_code = e.response.get("Error", {}).get("Code")
                if error_code != "ResourceInUseException":
                    log.warning("Aguardando DynamoDB local ficar pronto: %s", e)
                    time.sleep(1)
                    continue
            else:
                log.warning("Aguardando DynamoDB local ficar pronto: %s", e)
                time.sleep(1)
                continue

        while True:
            try:
                table = dynamodb_client.describe_table(TableName=DYNAMODB_TABLE_NAME)["Table"]
                if table.get("TableStatus") == "ACTIVE":
                    log.info(f"Tabela DynamoDB local '{DYNAMODB_TABLE_NAME}' está ativa.")
                    return
            except Exception as e:
                log.warning("Aguardando DynamoDB local ficar pronto: %s", e)
                break
            time.sleep(1)

    raise RuntimeError(f"Não foi possível preparar a tabela DynamoDB local '{DYNAMODB_TABLE_NAME}'")


# --- SQS Worker ---

def process_message(message):
    """ Processa uma única mensagem SQS e a insere no DynamoDB """
    try:
        log.info(f"Processando mensagem ID: {message['MessageId']}")
        body = json.loads(message['Body'])
        
        # Gera um ID único para o item no DynamoDB
        event_id = str(uuid.uuid4())
        
        # Constrói o item no formato do DynamoDB
        item = {
            'event_id': {'S': event_id},
            'user_id': {'S': body['user_id']},
            'flag_name': {'S': body['flag_name']},
            'result': {'BOOL': body['result']},
            'timestamp': {'S': body['timestamp']}
        }
        
        # Insere no DynamoDB
        dynamodb_client.put_item(
            TableName=DYNAMODB_TABLE_NAME,
            Item=item
        )
        
        log.info(f"Evento {event_id} (Flag: {body['flag_name']}) salvo no DynamoDB.")
        
        # Se tudo deu certo, deleta a mensagem da fila
        sqs_client.delete_message(
            QueueUrl=SQS_QUEUE_URL,
            ReceiptHandle=message['ReceiptHandle']
        )
        
    except json.JSONDecodeError:
        log.error(f"Erro ao decodificar JSON da mensagem ID: {message['MessageId']}")
        # Não deleta a mensagem, pode ser uma "poison pill"
    except ClientError as e:
        log.error(f"Erro do Boto3 (DynamoDB ou SQS) ao processar {message['MessageId']}: {e}")
        # Não deleta a mensagem, tenta novamente
    except Exception as e:
        log.error(f"Erro inesperado ao processar {message['MessageId']}: {e}")
        # Não deleta a mensagem, tenta novamente

def sqs_worker_loop():
    """ Loop principal do worker que ouve a fila SQS """
    log.info("Iniciando o worker SQS...")
    while True:
        try:
            # Long-polling: espera até 20s por mensagens
            response = sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=10,  # Processa em lotes de até 10
                WaitTimeSeconds=20
            )
            
            messages = response.get('Messages', [])
            if not messages:
                # Nenhuma mensagem, continua o loop
                continue
                
            log.info(f"Recebidas {len(messages)} mensagens.")
            
            for message in messages:
                process_message(message)
                
        except ClientError as e:
            log.error(f"Erro do Boto3 no loop principal do SQS: {e}")
            time.sleep(10) # Pausa antes de tentar novamente
        except Exception as e:
            log.error(f"Erro inesperado no loop principal do SQS: {e}")
            time.sleep(10)

# --- Servidor Flask (Apenas para Health Check) ---

app = Flask(__name__)

@app.route('/health')
def health():
    # Uma verificação de saúde real poderia checar a conexão com o DynamoDB/SQS
    return jsonify({"status": "ok"})

# --- Inicialização ---

def start_worker():
    """ Inicia o worker SQS em uma thread separada """
    worker_thread = threading.Thread(target=sqs_worker_loop, daemon=True)
    worker_thread.start()

# Garante que a tabela exista antes de iniciar o worker
ensure_dynamodb_table()

# Inicia o worker SQS em uma thread de background
# Isso garante que ele inicie tanto com 'flask run' quanto com 'gunicorn'
start_worker()

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8005))
    app.run(host='0.0.0.0', port=port, debug=False)
