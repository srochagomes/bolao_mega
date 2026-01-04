# Sincronização de Contador em Multiprocessing

## Problema Identificado

Com multiprocessing, cada worker process tinha uma **cópia local** do contador `first_number_counter`, o que causava:

1. **Visão desatualizada**: Cada worker via apenas o estado inicial do contador, não as atualizações de outros workers
2. **Inconsistência**: Múltiplos workers podiam gerar jogos que aumentavam a mesma região acima do target, porque não viam as atualizações em tempo real
3. **Agregação tardia**: Os incrementos só eram agregados após o batch completo, então durante a geração os workers tinham dados desatualizados

## Solução Implementada

### 1. CounterManager com Shared Memory + Persistência

Criado `backend/app/services/counter_manager.py` que:

- **Usa `multiprocessing.Manager()`**: Cria um dicionário compartilhado em memória
- **Lock para atomicidade**: Garante que atualizações sejam atômicas
- **Persistência em arquivo**: Salva estado em `backend/storage/metadata/first_number_counter.json`
- **Carregamento automático**: Se o arquivo existe, carrega o estado anterior

### 2. Sincronização em Tempo Real

**Antes (problema):**
```python
# Cada worker recebia uma CÓPIA do contador
first_number_counter = first_number_counter_dict.copy()
# Workers não viam atualizações de outros workers
current_counter = first_number_counter + worker_increments  # Desatualizado!
```

**Agora (solução):**
```python
# Workers usam contador COMPARTILHADO
with lock_proxy:
    current_counter = {num: shared_counter_proxy.get(num, 0) for num in range(1, 61)}
    # Workers veem atualizações em TEMPO REAL de todos os outros workers
```

### 3. Atualização Atômica

**Antes:**
```python
# Incrementos eram rastreados localmente e agregados depois
worker_counter_increments[first_number_selected] += 1
# Agregação só acontecia após batch completo
```

**Agora:**
```python
# Atualização imediata e atômica no contador compartilhado
with lock_proxy:
    shared_counter_proxy[first_number_selected] = shared_counter_proxy.get(first_number_selected, 0) + 1
# Todos os workers veem a atualização imediatamente
```

## Benefícios

1. **Sincronização em tempo real**: Todos os workers veem o estado atualizado do contador
2. **Validação precisa**: A validação de região usa dados atualizados de todos os workers
3. **Persistência**: Estado é salvo em arquivo, permitindo recuperação se o processo for interrompido
4. **Atomicidade**: Lock garante que não há race conditions

## Arquivos Modificados

1. **`backend/app/services/counter_manager.py`** (NOVO):
   - Gerencia contador compartilhado
   - Persistência em arquivo JSON
   - Lock para atomicidade

2. **`backend/app/services/generator_multiprocessing.py`**:
   - Usa `CounterManager` em vez de dicionário local
   - Workers acessam contador compartilhado com lock
   - Atualizações são atômicas e imediatas

## Como Funciona

1. **Inicialização**:
   - Cria `CounterManager` com arquivo de persistência
   - Cria contador compartilhado via `Manager().dict()`
   - Cria lock compartilhado via `Manager().Lock()`

2. **Durante geração**:
   - Cada worker acessa contador compartilhado com lock
   - Lê estado atual (vê atualizações de todos os workers)
   - Valida região baseado em estado atualizado
   - Atualiza contador atomicamente após gerar jogo

3. **Persistência**:
   - Salva a cada 100 incrementos (para evitar I/O excessivo)
   - Salva no final da geração
   - Carrega automaticamente se arquivo existe

## Localização do Arquivo

O arquivo de metadata é salvo em:
```
backend/storage/metadata/first_number_counter.json
```

Formato:
```json
{
  "counter": {
    "1": 877,
    "2": 833,
    ...
  },
  "total_generated": 10000
}
```

## Performance

- **Lock overhead**: Mínimo, pois cada worker só acessa o lock por milissegundos
- **Persistência**: Apenas a cada 100 incrementos, impacto mínimo
- **Memória compartilhada**: Mais eficiente que cópias locais para grandes volumes

## Conclusão

A solução resolve o problema de sincronização entre workers, garantindo que:
- Todos os workers veem o estado atualizado do contador
- A validação de região usa dados precisos
- O estado é persistido para recuperação
- Não há race conditions ou inconsistências

