# Exemplo de Integração do Ray no Sistema

## Como Usar

### 1. Instalar Ray

```bash
pip install ray
```

### 2. Modificar job_processor.py (opcional)

Adicionar suporte opcional ao Ray:

```python
# No início do arquivo
try:
    from app.services.generator_ray import GenerationEngineRay
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False

# No __init__ do JobProcessor
def __init__(self):
    # ... código existente ...
    
    # Usar Ray se disponível e para grandes quantidades
    self._use_ray = RAY_AVAILABLE
    if self._use_ray:
        self._generator_ray = GenerationEngineRay(use_ray=True)
        logger.info("Ray engine initialized")
    else:
        self._generator_ray = None
        logger.info("Ray not available, using sequential engine")

# No _process_job
async def _process_job(self, process_id: str, request: GenerationRequest):
    # ... código existente ...
    
    # Decidir qual engine usar
    use_ray = (
        self._use_ray and 
        request.quantity > 1000  # Usar Ray apenas para grandes quantidades
    )
    
    if use_ray:
        logger.info(f"Using Ray engine for {request.quantity} games")
        games = await loop.run_in_executor(
            self._executor,
            self._generator_ray.generate_games,
            request.quantity,
            request.constraints
        )
    else:
        # Usar engine sequencial normal
        if use_streaming:
            # ... código streaming existente ...
        else:
            games = await loop.run_in_executor(
                self._executor,
                self._generator.generate_games,
                request.quantity,
                request.constraints
            )
```

### 3. Adicionar ao requirements.txt

```txt
ray>=2.8.0  # Opcional - para processamento distribuído
```

## Benefícios

### Performance Esperada:

| Quantidade | Sequencial | Ray (4 cores) | Ray (8 cores) |
|------------|------------|---------------|---------------|
| 1.000 jogos | ~6s | ~2s | ~1s |
| 10.000 jogos | ~60s | ~15s | ~8s |
| 100.000 jogos | ~600s | ~150s | ~75s |

### Quando Usar Ray:

- ✅ Quantidades > 1.000 jogos
- ✅ Múltiplos núcleos disponíveis
- ✅ Quando performance é crítica

### Quando NÃO Usar Ray:

- ❌ Quantidades pequenas (< 100 jogos) - overhead não compensa
- ❌ Sistema com poucos recursos
- ❌ Quando simplicidade é mais importante

## Configuração Opcional

Adicionar configuração no `config.py`:

```python
# Processamento Distribuído
USE_RAY: bool = True  # Usar Ray se disponível
RAY_MIN_QUANTITY: int = 1000  # Usar Ray apenas para quantidades >= este valor
RAY_NUM_WORKERS: Optional[int] = None  # None = usar todos os cores
```

## Teste

```python
# Teste básico
from app.services.generator_ray import GenerationEngineRay
from app.models.generation import GameConstraints

engine = GenerationEngineRay(use_ray=True)
constraints = GameConstraints(numbers_per_game=6)
games = engine.generate_games(quantity=1000, constraints=constraints)
print(f"Gerados {len(games)} jogos")
engine.shutdown()
```

## Notas Importantes

1. **Ray inicializa automaticamente** quando importado pela primeira vez
2. **Serialização**: Ray serializa objetos Python automaticamente (usa pickle/cloudpickle)
3. **Memória**: Cada worker mantém seus próprios serviços (NumberGenerator, etc.)
4. **Shutdown**: Sempre chamar `engine.shutdown()` ao finalizar

## Alternativa: Dask

Se preferir Dask ao invés de Ray:

```python
from app.services.generator_dask import GenerationEngineDask

engine = GenerationEngineDask(use_dask=True)
games = engine.generate_games(quantity=1000, constraints=constraints)
engine.shutdown()
```

