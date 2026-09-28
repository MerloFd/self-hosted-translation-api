# Testa o container local (RIE), sem depender de nenhum backend.
# Uso:
#   .\test.ps1 "Hello world"                          # traduz uma frase en->pb
#   .\test.ps1 -Text "..." -Title "..."                # traduz texto + título juntos
#   .\test.ps1 -File materia.txt                       # traduz um arquivo .txt e cronometra

param(
  [string]$Text = "Hello world",
  [string]$Title = "",
  [string]$File,
  [string]$Source = "",
  [string]$Target = "pb"
)

if ($File) { $Text = Get-Content -Raw -Encoding utf8 $File }

$u = "http://localhost:9000/2015-03-31/functions/function/invocations"

$innerObj = @{ text = $Text; target = $Target }
if ($Title) { $innerObj.title = $Title }
if ($Source) { $innerObj.source = $Source }

$inner = $innerObj | ConvertTo-Json -Compress
$evt   = @{ body = $inner } | ConvertTo-Json -Compress

# IMPORTANTE: enviar como bytes UTF-8. O Invoke-RestMethod do PS 5.1 manda o corpo
# em Latin-1 por padrão, o que corrompe acentos/cirílico/CJK e quebra o RIE (utf-8 decode).
$bytes = [System.Text.Encoding]::UTF8.GetBytes($evt)

$t = Measure-Command { $global:r = Invoke-RestMethod -Uri $u -Method Post -Body $bytes -ContentType 'application/json; charset=utf-8' -TimeoutSec 600 }

"chars      : $($Text.Length)"
"tempo      : $([math]::Round($t.TotalSeconds,1))s"
if ($null -ne $global:r.statusCode) {
  "statusCode : $($global:r.statusCode)"
  $b = $global:r.body | ConvertFrom-Json
  "outcome    : $($b.outcome)"
  "source     : $($b.detected_source)"
  if ($b.translated_text) { "texto      : $($b.translated_text)" }
  if ($b.translated_title) { "titulo     : $($b.translated_title)" }
  if ($b.error) { "erro       : $($b.error)" }
} else {
  # RIE devolveu erro de runtime (sem statusCode/body)
  "ERRO RIE   : " + ($global:r | ConvertTo-Json -Compress -Depth 5)
}
