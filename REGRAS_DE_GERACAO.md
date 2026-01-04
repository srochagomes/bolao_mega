# Regras de Geração de Jogos - Mega-Sena

Este documento lista todas as regras aplicadas pelo sistema quando o usuário escolhe gerar jogos.

## 📋 Regras Fundamentais (Nunca Relaxadas)

### 1. Validação Básica
- ✅ **Quantidade de números**: Deve ter exatamente o número solicitado (padrão: 6)
- ✅ **Números únicos**: Não pode ter números repetidos
- ✅ **Faixa válida**: Todos os números devem estar entre 1 e 60
- ✅ **Números fixos**: Se o usuário forneceu números fixos, o jogo deve usar APENAS esses números

### 2. Dados Históricos (FUNDAMENTAL - NUNCA RELAXADO)
- ❌ **Jogo já sorteado**: Não pode ser idêntico a um jogo já sorteado no histórico
- ❌ **Quina**: Não pode ter 5 números iguais a um jogo histórico (quina)
- ❌ **Últimos 2 sorteios**: Máximo de 2 números podem estar entre o último e penúltimo sorteio

## 📊 Regras de Padrões (Relaxadas Progressivamente)

### 3. Padrões Sequenciais Extremos
**Níveis: STRICT, NORMAL** (desabilitada em RELAXED/MINIMAL)
- ❌ **Sequência extrema**: Não pode ser 1-2-3-4-5-6 ou 55-56-57-58-59-60

### 4. Números Consecutivos
**Níveis: STRICT, NORMAL, RELAXED** (desabilitada em MINIMAL)
- ❌ **4+ consecutivos**: Não pode ter 4 ou mais números consecutivos
  - Exemplo: [1, 2, 3, 4, 10, 20] ❌ (tem 1-2-3-4)
  - Exemplo: [1, 2, 5, 10, 20, 30] ✅ (máximo 2 consecutivos)

### 5. Distribuição Ímpar/Par
**Níveis: STRICT, NORMAL** (relaxada em RELAXED/MINIMAL)
- ❌ **Todos ímpares ou todos pares**: Não pode ter todos os números ímpares ou todos pares
  - Exemplo: [1, 3, 5, 7, 9, 11] ❌ (todos ímpares)
  - Exemplo: [2, 4, 6, 8, 10, 12] ❌ (todos pares)
  - Exemplo: [1, 2, 3, 4, 5, 6] ✅ (misturado)

## 🎯 Regras de Repetição (Apenas quando NÃO há números fixos)

### 6. Repetição de Ternos (3 números consecutivos)
**Aplicada apenas quando o usuário NÃO fornece números fixos**

**Janela**: Últimos 5000 jogos gerados

| Nível | Máximo de Repetições |
|-------|---------------------|
| STRICT | 2 repetições |
| NORMAL | 2 repetições |
| RELAXED | 3 repetições |
| MINIMAL | 4 repetições |

**Exemplo**:
- Se o terno (1, 2, 3) já apareceu 2 vezes nos últimos 5000 jogos (STRICT), não pode aparecer novamente
- Se apareceu apenas 1 vez, pode aparecer mais 1 vez

### 7. Repetição de Duplas (pares de números)
**Aplicada apenas quando o usuário NÃO fornece números fixos**

**Janela**: Últimos 500 jogos gerados

| Nível | Máximo de Repetições |
|-------|---------------------|
| STRICT | 2 repetições |
| NORMAL | 2 repetições |
| RELAXED | 3 repetições |
| MINIMAL | 4 repetições |

**Exemplo**:
- Se a dupla (1, 2) já apareceu 2 vezes nos últimos 500 jogos (STRICT), não pode aparecer novamente
- Se apareceu apenas 1 vez, pode aparecer mais 1 vez

## 📈 Regras de Distribuição Estatística

### 8. Distribuição da Primeira Dezena
**Baseada na frequência histórica real**

- ✅ **Análise do histórico**: O sistema analisa qual região (1-10, 11-20, 21-30, etc.) tem mais frequência como primeira dezena
- ✅ **Pesos dinâmicos**: Os pesos são calculados DIRETAMENTE da frequência relativa do histórico
  - Se número 10 apareceu 119 vezes em 3000 sorteios → peso = 119/3000 = 0.0397 (3.97%)
  - Se número 1 apareceu 263 vezes em 3000 sorteios → peso = 263/3000 = 0.0877 (8.77%)
- ✅ **Ajuste dinâmico**: Durante a geração, o sistema ajusta pesos em tempo real para corrigir desvios
  - Se já gerou 30%+ acima do target: reduz peso para 5%
  - Se ainda não gerou 30% do target: aumenta peso 4x
- ✅ **Sem regras fixas**: Não há regras específicas para números 1-9; tudo é baseado no histórico

### 9. Repetição de Jogos Completos
- ❌ **Jogo duplicado**: Não pode gerar um jogo idêntico a um já gerado
- ✅ **Verificação O(1)**: Usa um conjunto (set) para verificação rápida contra TODOS os jogos já gerados

### 10. Repetição de Números (se especificado)
**Aplicada apenas se o usuário especificar min_repetition ou max_repetition**

- ✅ **min_repetition**: Jogo deve ter pelo menos X números em comum com jogos anteriores
- ✅ **max_repetition**: Jogo deve ter no máximo X números em comum com jogos anteriores
- ✅ **Janela**: Verifica apenas os últimos 100 jogos para performance

## 🎚️ Níveis de Validação (Adaptativos)

O sistema usa níveis adaptativos que relaxam regras progressivamente quando há dificuldade:

### STRICT (Estrito)
- **Ativado**: 0-2 falhas consecutivas
- **Regras**: Todas as regras ativas
- **Ternos**: Máx 2 repetições
- **Duplas**: Máx 2 repetições

### NORMAL (Normal)
- **Ativado**: 3-7 falhas consecutivas
- **Regras**: Mesmas do STRICT
- **Ternos**: Máx 2 repetições
- **Duplas**: Máx 2 repetições

### RELAXED (Relaxado)
- **Ativado**: 8-14 falhas consecutivas
- **Regras**: Desabilita padrões extremos, relaxa ímpar/par
- **Ternos**: Máx 3 repetições
- **Duplas**: Máx 3 repetições

### MINIMAL (Mínimo)
- **Ativado**: 15+ falhas consecutivas
- **Regras**: Apenas regras fundamentais (histórico sempre ativo)
- **Ternos**: Máx 4 repetições (ou desabilitado)
- **Duplas**: Máx 4 repetições (ou desabilitado)
- **Consecutivos**: Desabilitado
- **Ímpar/Par**: Desabilitado

## 🔄 Comportamento Especial

### Quando o usuário fornece números fixos:
- ✅ **Ternos/Duplas**: Regras de repetição de ternos/duplas são **DESABILITADAS**
- ✅ **Distribuição**: Sistema foca em gerar boa distribuição usando apenas os números fornecidos
- ✅ **Primeira dezena**: Não aplica regra de distribuição da primeira dezena (usa números fixos)

### Quando o usuário NÃO fornece números fixos:
- ✅ **Ternos/Duplas**: Regras de repetição são **ATIVAS**
- ✅ **Distribuição**: Sistema usa frequência histórica para distribuir primeira dezena
- ✅ **Ajuste dinâmico**: Contador compartilhado ajusta pesos em tempo real

## 📊 Pontuação de Jogos

O sistema pontua jogos baseado em:
- ✅ **Distribuição ímpar/par**: Jogos balanceados recebem pontuação maior
- ✅ **Validação básica**: Jogos que passam todas as validações recebem pontuação base
- ✅ **Threshold**: Jogos com pontuação >= threshold são aceitos (varia por nível)

## 🚀 Otimizações

- ✅ **Cache incremental**: Validação de ternos/duplas usa cache O(1) em vez de O(n²)
- ✅ **Janelas deslizantes**: Mantém apenas últimos 5000 jogos (ternos) e 500 jogos (duplas)
- ✅ **Verificação de duplicatas**: Usa set para verificação O(1) contra todos os jogos
- ✅ **Processamento paralelo**: Usa multiprocessing para gerar jogos em paralelo

## 📝 Resumo das Regras por Prioridade

### 🔴 Prioridade MÁXIMA (Nunca Relaxadas)
1. Validação básica (quantidade, unicidade, faixa)
2. Dados históricos (jogo já sorteado, quina, últimos 2 sorteios)
3. Jogos completamente duplicados

### 🟠 Prioridade ALTA (Relaxadas em MINIMAL)
4. Números consecutivos (4+)
5. Padrões sequenciais extremos

### 🟡 Prioridade MÉDIA (Relaxadas em RELAXED/MINIMAL)
6. Distribuição ímpar/par (todos ímpar ou todos par)
7. Repetição de ternos (quando sem números fixos)
8. Repetição de duplas (quando sem números fixos)

### 🟢 Prioridade BAIXA (Ajuste Dinâmico)
9. Distribuição da primeira dezena (baseada no histórico)
10. Repetição de números (se especificado pelo usuário)

