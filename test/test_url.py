
from util.disa_connection import DisaConnection

import logging

logging.basicConfig(
    filename='call.log',  # Nombre del archivo de logs
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Nivel de logging, por ejemplo DEBUG, INFO, ERROR
)

logger = logging.getLogger(__name__)

DisaConnection.call_first_url("+8332866392", "+16204222259")
