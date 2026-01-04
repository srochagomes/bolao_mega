# Nova Estratégia: Análise de Regiões para Distribuição da Primeira Dezena

## Problema Identificado

O sistema estava gerando muitos jogos começando com números 1-9, mesmo quando o histórico mostra distribuição diferente. Além disso, havia um problema onde o sistema gerava o primeiro número com pesos, mas depois colocava o número 1 em segundo ou último, e quando ordenava, o número 1 ficava em primeiro.

## Nova Estratégia Implementada

### 1. Análise de Regiões ANTES de Gerar

O sistema agora analisa o histórico ANTES de gerar qualquer jogo:

- **Regiões de 3 números**: 1-3, 4-6, 7-9, 10-12, 13-15, 16-18, 19-21, 22-24, 25-27, 28-30, etc.
- **Pontuação por frequência**: Cada região recebe uma pontuação baseada na frequência histórica da primeira dezena
- **Melhores regiões primeiro**: As regiões são ordenadas por frequência (melhores primeiro)

### 2. Geração Randomica → Ordenação → Validação

O fluxo agora é:

1. **Gerar números randomicamente** (sem ordenar ainda)
   - Usa pesos baseados na análise de regiões
   - Não garante que o primeiro número selecionado seja o menor

2. **Ordenar os números**
   - Após gerar, ordena os números
   - Identifica qual número realmente ficou em primeiro (menor número)

3. **Verificar região da primeira dezena**
   - Identifica em qual região está o menor número (após ordenação)
   - Exemplo: Se o menor número é 5, está na região 4-6

4. **Validar distribuição**
   - Calcula quantos jogos já foram gerados em cada região
   - Compara com o target histórico
   - Se a região está mais de 30% acima do target, **rejeita o jogo**

5. **Gerar novamente se rejeitado**
   - Se o jogo foi rejeitado, tenta gerar novamente
   - O ajuste dinâmico garante que regiões muito frequentes tenham menos chance

### 3. Arquivos Criados/Modificados

#### Novo Arquivo: `backend/app/services/region_analyzer.py`
- Classe `RegionAnalyzer`: Analisa histórico e identifica melhores regiões
- Método `analyze_regions()`: Retorna regiões ordenadas por frequência
- Método `get_region_for_number()`: Identifica região de um número
- Método `get_target_distribution()`: Retorna distribuição desejada baseada em regiões

#### Modificado: `backend/app/services/number_generator.py`
- Método `_generate_without_fixed_numbers()`: Implementa nova estratégia
  - Gera randomicamente
  - Ordena
  - Valida região
  - Rejeita se necessário

#### Modificado: `backend/app/services/generator.py`
- Usa `region_analyzer` para obter distribuição desejada
- Log das melhores regiões identificadas

#### Modificado: `backend/app/services/generator_multiprocessing.py`
- Usa `region_analyzer` para obter distribuição desejada
- Trata rejeição de jogos (None, None)

## Como Funciona

### Exemplo de Análise de Regiões

```
Região 1-3:   263 vezes (8.77%) - Melhor região
Região 4-6:   250 vezes (8.33%)
Região 7-9:   243 vezes (8.10%)
Região 10-12: 119 vezes (3.97%)
...
```

### Exemplo de Validação

1. Jogo gerado: [5, 12, 25, 30, 45, 50]
2. Após ordenação: [5, 12, 25, 30, 45, 50]
3. Primeira dezena: 5
4. Região: 4-6 (target: 8.33%)
5. Verificar: Já foram gerados 850 jogos na região 4-6 de 10.000 total (8.5%)
6. Ratio: 8.5% / 8.33% = 1.02x (dentro do limite de 1.3x)
7. **Aceitar jogo**

### Exemplo de Rejeição

1. Jogo gerado: [1, 10, 25, 30, 45, 50]
2. Após ordenação: [1, 10, 25, 30, 45, 50]
3. Primeira dezena: 1
4. Região: 1-3 (target: 8.77%)
5. Verificar: Já foram gerados 1.200 jogos na região 1-3 de 10.000 total (12.0%)
6. Ratio: 12.0% / 8.77% = 1.37x (acima do limite de 1.3x)
7. **Rejeitar jogo e gerar novamente**

## Benefícios

1. **Evita problema de ordenação**: O sistema não assume que o primeiro número selecionado será o menor
2. **Validação baseada em regiões**: Valida a distribuição por região, não apenas por número individual
3. **Ajuste dinâmico mais eficaz**: Rejeita jogos que não atendem à distribuição desejada
4. **Baseado em análise prévia**: Analisa o histórico ANTES de gerar, não durante

## Próximos Passos

1. Testar com 10.000 jogos
2. Verificar se a distribuição está próxima do histórico
3. Ajustar threshold de rejeição (atualmente 30%) se necessário
4. Monitorar performance (quantos jogos são rejeitados)

