param(
    [Parameter(Mandatory = $true)]
    [string]$RibbonDiffPath,

    [Parameter(Mandatory = $true)]
    [string]$TableLogicalName,

    [Parameter(Mandatory = $true)]
    [string]$ButtonLabel,

    [Parameter(Mandatory = $true)]
    [string]$JavaScriptLibraryWebResourceName,

    [Parameter(Mandatory = $true)]
    [string]$JavaScriptFunctionName,

    [Parameter(Mandatory = $false)]
    [string]$PublisherPrefix = 'new',

    [Parameter(Mandatory = $false)]
    [int]$Sequence = 100,

    [Parameter(Mandatory = $false)]
    [string]$Image16by16WebResourceName,

    [Parameter(Mandatory = $false)]
    [string]$Image32by32WebResourceName,

    [Parameter(Mandatory = $false)]
    [bool]$PassPrimaryControl = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function New-XmlDocument {
    $xmlText = @"
<?xml version="1.0" encoding="utf-8"?>
<RibbonDiffXml xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <CustomActions />
  <Templates>
    <RibbonTemplates Id="Mscrm.Templates" />
  </Templates>
  <CommandDefinitions />
  <RuleDefinitions>
    <TabDisplayRules />
    <DisplayRules />
    <EnableRules />
  </RuleDefinitions>
  <LocLabels />
</RibbonDiffXml>
"@
    $doc = New-Object System.Xml.XmlDocument
    $doc.PreserveWhitespace = $true
    $doc.LoadXml($xmlText)
    return $doc
}

function Get-OrCreateChildElement([System.Xml.XmlNode]$Parent, [string]$Name) {
    $node = $Parent.SelectSingleNode("./$Name")
    if (-not $node) {
        $node = $Parent.OwnerDocument.CreateElement($Name)
        [void]$Parent.AppendChild($node)
    }
    return $node
}

function Remove-NodeById([System.Xml.XmlNode]$Root, [string]$XPath, [string]$Id) {
    $nodes = $Root.SelectNodes($XPath.Replace('{id}', $Id))
    foreach ($node in $nodes) {
        if ($node.ParentNode) {
            [void]$node.ParentNode.RemoveChild($node)
        }
    }
}

function ConvertTo-IdPrefix([string]$Prefix) {
    $value = ($Prefix -replace '[^A-Za-z0-9_.-]', '')
    $value = $value.Trim('.', '_', '-')
    if ([string]::IsNullOrWhiteSpace($value)) { return 'new' }
    return $value
}

function New-Slug([string]$Text) {
    $value = $Text.ToLowerInvariant()
    $value = [regex]::Replace($value, '[^a-z0-9]+', '')
    if ([string]::IsNullOrWhiteSpace($value)) { return 'button' }
    return $value
}

function ConvertTo-WebResourceDirective([string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Name)) { return $null }
    if ($Name.StartsWith('$webresource:', [System.StringComparison]::OrdinalIgnoreCase)) {
        return $Name
    }
    return '$webresource:' + $Name
}

function Resolve-EntityToken([string]$RibbonPath, [string]$FallbackTableLogicalName) {
    $folder = Split-Path -Parent $RibbonPath
    $entityXmlPath = Join-Path $folder 'Entity.xml'

    if (Test-Path $entityXmlPath) {
        try {
            [xml]$entityXml = Get-Content -Path $entityXmlPath -Raw -Encoding UTF8
            $entityNode = $entityXml.SelectSingleNode('/Entity/EntityInfo/entity')
            if ($entityNode -and $entityNode.Attributes['Name']) {
                return $entityNode.Attributes['Name'].Value.ToLowerInvariant()
            }
        }
        catch {
            Write-Warning "Could not parse Entity.xml at '$entityXmlPath'. Falling back to TableLogicalName."
        }
    }

    return $FallbackTableLogicalName.ToLowerInvariant()
}

$tableToken = Resolve-EntityToken -RibbonPath $RibbonDiffPath -FallbackTableLogicalName $TableLogicalName
$containerLocation = "Mscrm.Form.$tableToken.MainTab.Actions.Controls._children"

$image16 = ConvertTo-WebResourceDirective $Image16by16WebResourceName
$image32 = ConvertTo-WebResourceDirective $Image32by32WebResourceName
$javaScriptLibrary = ConvertTo-WebResourceDirective $JavaScriptLibraryWebResourceName

if (-not $image16 -and $image32) { $image16 = $image32 }
if (-not $image32 -and $image16) { $image32 = $image16 }
if (-not $javaScriptLibrary) {
    throw 'JavaScriptLibraryWebResourceName must resolve to a web resource directive.'
}
if ([string]::IsNullOrWhiteSpace($JavaScriptFunctionName)) {
    throw 'JavaScriptFunctionName cannot be empty.'
}

$idPrefix = ConvertTo-IdPrefix $PublisherPrefix
$slug = New-Slug $ButtonLabel
$idBase = "$idPrefix.$tableToken.mainForm.$slug"
$customActionId = "$idBase.CustomAction"
$commandId = "$idBase.Command"
$buttonId = "$idBase.Button"

$doc = if (Test-Path $RibbonDiffPath) {
    $x = New-Object System.Xml.XmlDocument
    $x.PreserveWhitespace = $true
    $x.Load($RibbonDiffPath)
    $x
}
else {
    New-XmlDocument
}

$root = $doc.DocumentElement
if (-not $root -or $root.Name -ne 'RibbonDiffXml') {
    throw "The file '$RibbonDiffPath' is not a RibbonDiffXml document."
}

$customActions = Get-OrCreateChildElement -Parent $root -Name 'CustomActions'
$templates = Get-OrCreateChildElement -Parent $root -Name 'Templates'
$ribbonTemplates = Get-OrCreateChildElement -Parent $templates -Name 'RibbonTemplates'
if (-not $ribbonTemplates.Attributes['Id']) {
    $attr = $doc.CreateAttribute('Id')
    $attr.Value = 'Mscrm.Templates'
    [void]$ribbonTemplates.Attributes.Append($attr)
}
$commandDefinitions = Get-OrCreateChildElement -Parent $root -Name 'CommandDefinitions'
$ruleDefinitions = Get-OrCreateChildElement -Parent $root -Name 'RuleDefinitions'
[void](Get-OrCreateChildElement -Parent $ruleDefinitions -Name 'TabDisplayRules')
[void](Get-OrCreateChildElement -Parent $ruleDefinitions -Name 'DisplayRules')
[void](Get-OrCreateChildElement -Parent $ruleDefinitions -Name 'EnableRules')
[void](Get-OrCreateChildElement -Parent $root -Name 'LocLabels')

Remove-NodeById -Root $root -XPath "./CustomActions/CustomAction[@Id='{id}']" -Id $customActionId
Remove-NodeById -Root $root -XPath "./CommandDefinitions/CommandDefinition[@Id='{id}']" -Id $commandId

$customAction = $doc.CreateElement('CustomAction')
$customAction.SetAttribute('Id', $customActionId)
$customAction.SetAttribute('Location', $containerLocation)
$customAction.SetAttribute('Sequence', [string]$Sequence)

$commandUiDefinition = $doc.CreateElement('CommandUIDefinition')
$button = $doc.CreateElement('Button')
$button.SetAttribute('Id', $buttonId)
$button.SetAttribute('Command', $commandId)
$button.SetAttribute('LabelText', $ButtonLabel)
$button.SetAttribute('ToolTipTitle', $ButtonLabel)
$button.SetAttribute('ToolTipDescription', $ButtonLabel)
$button.SetAttribute('Sequence', [string]$Sequence)
$button.SetAttribute('TemplateAlias', 'o1')

if ($image16) { $button.SetAttribute('Image16by16', $image16) }
if ($image32) { $button.SetAttribute('Image32by32', $image32) }

[void]$commandUiDefinition.AppendChild($button)
[void]$customAction.AppendChild($commandUiDefinition)
[void]$customActions.AppendChild($customAction)

$commandDefinition = $doc.CreateElement('CommandDefinition')
$commandDefinition.SetAttribute('Id', $commandId)
[void]$commandDefinition.AppendChild($doc.CreateElement('EnableRules'))

$actions = $doc.CreateElement('Actions')
$javaScriptFunction = $doc.CreateElement('JavaScriptFunction')
$javaScriptFunction.SetAttribute('Library', $javaScriptLibrary)
$javaScriptFunction.SetAttribute('FunctionName', $JavaScriptFunctionName)
if ($PassPrimaryControl) {
    $crmParameter = $doc.CreateElement('CrmParameter')
    $crmParameter.SetAttribute('Value', 'PrimaryControl')
    [void]$javaScriptFunction.AppendChild($crmParameter)
}
[void]$actions.AppendChild($javaScriptFunction)
[void]$commandDefinition.AppendChild($actions)
[void]$commandDefinitions.AppendChild($commandDefinition)

$settings = New-Object System.Xml.XmlWriterSettings
$settings.Indent = $true
$settings.IndentChars = '  '
$settings.NewLineChars = "`r`n"
$settings.NewLineHandling = 'Replace'
$settings.OmitXmlDeclaration = $false

$writer = [System.Xml.XmlWriter]::Create($RibbonDiffPath, $settings)
$doc.Save($writer)
$writer.Dispose()

Write-Host 'Patched RibbonDiffXml for entity main form command bar.'
Write-Host "  File: $RibbonDiffPath"
Write-Host "  Table token: $tableToken"
Write-Host "  Container: $containerLocation"
Write-Host "  CustomAction Id: $customActionId"
Write-Host "  Button Id: $buttonId"
Write-Host "  Command Id: $commandId"
Write-Host "  JavaScript library: $javaScriptLibrary"
Write-Host "  JavaScript function: $JavaScriptFunctionName"
Write-Host "  Pass PrimaryControl: $PassPrimaryControl"
if ($image16 -or $image32) {
    Write-Host "  Button icons: 16=$image16 ; 32=$image32"
}
else {
    Write-Host '  Button icons: <none>'
}
