# Estratégia de Distribuição da Primeira Dezena

## Problema Identificado

O sistema estava gerando muitos jogos começando com números 1-9 (especialmente 1, 2, 3), mesmo quando o histórico mostra que esses números não são os mais frequentes como primeira dezena.

**Exemplo do problema:**
- Número 1: Gerado 12.24% vs Histórico 8.77% = **+40% acima do target**
- Número 2: Gerado 11.27% vs Histórico 8.33% = **+35% acima do target**

## Causa Raiz

O problema estava na lógica de seleção da primeira dezena:

1. **Uso direto da frequência histórica**: O sistema usava a frequência histórica diretamente como peso, o que fazia números com frequência alta (1, 2, 3) terem muito mais chance de serem selecionados desde o início.

2. **Ajuste dinâmico só após primeiro jogo**: O ajuste dinâmico só era aplicado quando `total_generated > 0`, então no primeiro jogo todos os números usavam a frequência histórica pura.

3. **Ajuste não suficientemente agressivo**: Mesmo quando o ajuste dinâmico era aplicado, ele não era agressivo o suficiente para corrigir rapidamente os desvios.

## Nova Estratégia Implementada

### 1. Distribuição Quase Uniforme no Início

Quando `total_generated = 0` (início da geração), o sistema agora usa uma **distribuição quase uniforme** (1/60 para todos os números) em vez da frequência histórica direta:

- **Números com frequência > 8%** (1, 2, 3): Usam apenas **60% do peso uniforme**
- **Números com frequência 7-8%** (4): Usam **70% do peso uniforme**
- **Números com frequência 5-7%** (5, 6, 7, 8): Usam **85% do peso uniforme**
- **Números com frequência < 5%**: Usam **110% do peso uniforme** (ligeira preferência)

Isso garante que no início, todos os números tenham chance similar, evitando que números muito frequentes dominem desde o começo.

### 2. Ajuste Dinâmico Muito Mais Agressivo

Quando `total_generated > 0`, o sistema aplica ajuste dinâmico baseado no desvio atual:

**Redução (quando acima do target):**
- **> 40% acima**: Reduz peso para **1%** (extremamente agressivo)
- **> 30% acima**: Reduz peso para **5%**
- **> 20% acima**: Reduz peso para **15%**
- **> 10% acima**: Reduz peso para **40%**
- **> 5% acima**: Reduz peso para **70%**

**Aumento (quando abaixo do target):**
- **< 30% do target**: Aumenta peso **5x** (muito agressivo)
- **< 50% do target**: Aumenta peso **3x**
- **< 70% do target**: Aumenta peso **2x**
- **< 90% do target**: Aumenta peso **1.5x**

### 3. Fluxo Completo

```
1. Início (total_generated = 0):
   → Usa distribuição quase uniforme (reduzida para números muito frequentes)
   
2. Após primeiro jogo (total_generated > 0):
   → Calcula desvio: current_ratio / target_ratio
   → Aplica ajuste agressivo baseado no desvio
   → Seleciona primeira dezena com pesos ajustados
   
3. Continua ajustando dinamicamente:
   → A cada jogo gerado, recalcula desvios
   → Ajusta pesos para corrigir distribuição
   → Consegue atingir distribuição próxima do histórico
```

## Arquivos Modificados

1. **`backend/app/services/number_generator.py`**:
   - Método `_generate_without_fixed_numbers` modificado
   - Nova lógica de distribuição quase uniforme no início
   - Ajuste dinâmico muito mais agressivo

2. **`frontend/components/GenerationForm.tsx`**:
   - Adicionado radio button para escolher entre "Números Aleatórios" e "Números Fixos"
   - Campo de números fixos só aparece quando modo "fixo" é selecionado

## Como Testar

1. **Gerar 10.000 jogos** usando modo "Números Aleatórios"
2. **Abrir o Excel gerado** e verificar a distribuição da primeira dezena
3. **Comparar com histórico**:
   - Número 1: Deve estar entre 6.1% e 11.4% (70% a 130% de 8.77%)
   - Número 2: Deve estar entre 5.8% e 10.8% (70% a 130% de 8.33%)
   - Número 10: Deve estar entre 2.8% e 5.2% (70% a 130% de 3.97%)

## Próximos Passos

Se ainda houver problemas:

1. **Aumentar ainda mais a redução inicial** para números muito frequentes (de 60% para 40%)
2. **Aplicar ajuste dinâmico desde o primeiro jogo** (não esperar total_generated > 0)
3. **Usar distribuição completamente uniforme** no início (1/60 para todos, sem preferências)

