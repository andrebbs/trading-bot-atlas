"""
Cliente HTTP para integração com Tess (Pareto IA Platform).
Suporta autenticação via API Key, retry automático com backoff exponencial,
e logging estruturado de tentativas.

Documentação esperada da Tess:
- Base URL: https://api.tess.pareto.ai/v1 (ou similar)
- Endpoint: POST /messages/send ou POST /agents/execute
- Autenticação: Header "Authorization: Bearer {TESS_API_KEY}"
- Payload JSON: { "recipient", "message" | "template", "data" (opcional), "channel" }
- Response: { "id", "status", "timestamp", "error" (opcional) }
"""

import os
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class MessageChannel(Enum):
    """Canais suportados pela Tess."""
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"
    TELEGRAM = "telegram"  # Se Tess suportar


@dataclass
class TessMessage:
    """Modelo de mensagem para envio via Tess."""
    recipient: str  # Número, e-mail ou ID do usuário
    content: str  # Conteúdo da mensagem
    channel: MessageChannel = MessageChannel.WHATSAPP
    template_id: Optional[str] = None  # Se usar template
    variables: Optional[Dict[str, Any]] = None  # Variáveis para personalização
    metadata: Optional[Dict[str, Any]] = None  # Dados adicionais

    def to_payload(self) -> Dict[str, Any]:
        """Converte para payload JSON esperado pela Tess."""
        payload = {
            "recipient": self.recipient,
            "channel": self.channel.value,
        }
        
        if self.template_id:
            payload["template_id"] = self.template_id
            payload["data"] = self.variables or {}
        else:
            payload["message"] = self.content

        if self.metadata:
            payload["metadata"] = self.metadata

        return payload


@dataclass
class TessResponse:
    """Resposta padrão da Tess."""
    success: bool
    message_id: Optional[str] = None
    status: Optional[str] = None  # 'pending', 'sent', 'delivered', 'failed'
    timestamp: Optional[str] = None
    error: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class TessClient:
    """Cliente HTTP para Tess com retry automático e logging."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_retries: int = 3,
        retry_backoff_factor: float = 2.0,
        timeout_seconds: int = 10,
    ):
        """
        Inicializa cliente Tess.
        
        Args:
            api_key: API Key da Tess (ou env: TESS_API_KEY)
            base_url: URL base da API (ou env: TESS_BASE_URL)
            max_retries: Número máximo de tentativas
            retry_backoff_factor: Fator multiplicador para backoff exponencial
            timeout_seconds: Timeout para requisições HTTP
        """
        self.api_key = api_key or os.getenv("TESS_API_KEY", "").strip()
        self.base_url = (base_url or os.getenv("TESS_BASE_URL", "")).rstrip("/")
        self.max_retries = max_retries
        self.retry_backoff_factor = retry_backoff_factor
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        
        self._validate_config()

    def _validate_config(self) -> None:
        """Valida se configuração está disponível."""
        if not self.api_key:
            raise ValueError("TESS_API_KEY não configurada. Verifique variável de ambiente.")
        if not self.base_url:
            raise ValueError("TESS_BASE_URL não configurada. Verifique variável de ambiente.")
        
        logger.info(f"✅ Cliente Tess inicializado: {self.base_url}")

    def _get_headers(self) -> Dict[str, str]:
        """Retorna headers com autenticação."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "TessClient/1.0",
        }

    def _backoff_delay(self, attempt: int) -> float:
        """Calcula delay com backoff exponencial."""
        return min(
            self.retry_backoff_factor ** attempt + (time.time() % 1),  # jitter
            60,  # max 60s
        )

    def send_message(
        self,
        message: TessMessage,
        endpoint: str = "/messages/send",
    ) -> TessResponse:
        """
        Envia mensagem via Tess com retry automático.
        
        Args:
            message: Instância de TessMessage
            endpoint: Endpoint da API (padrão: /messages/send)
        
        Returns:
            TessResponse com resultado do envio
        """
        url = f"{self.base_url}{endpoint}"
        payload = message.to_payload()
        
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(
                    f"[Tess] Tentativa {attempt + 1}/{self.max_retries}: "
                    f"{message.recipient} via {message.channel.value}"
                )
                
                response = self.session.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=self.timeout_seconds,
                )
                
                # Parse resposta
                response_data = response.json()
                
                if response.status_code in (200, 201):
                    return TessResponse(
                        success=True,
                        message_id=response_data.get("id"),
                        status=response_data.get("status", "sent"),
                        timestamp=response_data.get("timestamp"),
                        raw_response=response_data,
                    )
                else:
                    error_msg = response_data.get("error", "HTTP " + str(response.status_code))
                    logger.warning(
                        f"[Tess] Erro {response.status_code}: {error_msg} "
                        f"(tentativa {attempt + 1})"
                    )
                    last_error = error_msg
                    
            except requests.Timeout:
                last_error = f"Timeout ({self.timeout_seconds}s)"
                logger.warning(f"[Tess] {last_error} em tentativa {attempt + 1}")
                
            except requests.ConnectionError as e:
                last_error = f"Erro conexão: {str(e)}"
                logger.warning(f"[Tess] {last_error}")
                
            except ValueError as e:
                last_error = f"Erro parsing JSON: {str(e)}"
                logger.error(f"[Tess] {last_error}")
                break  # Não faz sentido retry em parse error
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"[Tess] Erro inesperado: {last_error}")
                break
            
            # Aguarda antes de retry (exceto última tentativa)
            if attempt < self.max_retries - 1:
                delay = self._backoff_delay(attempt)
                logger.info(f"[Tess] Aguardando {delay:.1f}s antes da próxima tentativa...")
                time.sleep(delay)
        
        # Todas as tentativas falharam
        logger.error(
            f"[Tess] Falha após {self.max_retries} tentativas. "
            f"Erro final: {last_error}"
        )
        return TessResponse(
            success=False,
            error=last_error,
            status="failed",
        )

    def send_agent_message(
        self,
        agent_id: str,
        recipient: str,
        message: str,
        channel: MessageChannel = MessageChannel.WHATSAPP,
    ) -> TessResponse:
        """
        Atalho para envio via agente (se Tess suportar).
        
        Args:
            agent_id: ID do agente a executar
            recipient: Destinatário
            message: Mensagem/prompt para o agente
            channel: Canal de envio
        
        Returns:
            TessResponse
        """
        payload = {
            "agent_id": agent_id,
            "recipient": recipient,
            "message": message,
            "channel": channel.value,
        }
        
        url = f"{self.base_url}/agents/execute"
        
        try:
            response = self.session.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.timeout_seconds,
            )
            response_data = response.json()
            
            if response.status_code in (200, 201):
                return TessResponse(
                    success=True,
                    message_id=response_data.get("id"),
                    status=response_data.get("status", "executed"),
                    timestamp=response_data.get("timestamp"),
                    raw_response=response_data,
                )
            else:
                return TessResponse(
                    success=False,
                    error=response_data.get("error", f"HTTP {response.status_code}"),
                    status="failed",
                )
        except Exception as e:
            logger.error(f"[Tess] Erro ao executar agente: {e}")
            return TessResponse(success=False, error=str(e), status="failed")

    def health_check(self) -> bool:
        """Verifica se API está acessível."""
        try:
            url = f"{self.base_url}/health"
            response = self.session.get(
                url,
                headers=self._get_headers(),
                timeout=self.timeout_seconds,
            )
            is_healthy = response.status_code == 200
            logger.info(f"[Tess] Health check: {'✅ OK' if is_healthy else '❌ ERRO'}")
            return is_healthy
        except Exception as e:
            logger.error(f"[Tess] Health check falhou: {e}")
            return False

    def close(self) -> None:
        """Fecha sessão HTTP."""
        self.session.close()


# Singleton global (opcional)
_tess_client: Optional[TessClient] = None


def get_tess_client() -> TessClient:
    """Retorna instância global de TessClient (lazy init)."""
    global _tess_client
    if _tess_client is None:
        _tess_client = TessClient()
    return _tess_client
