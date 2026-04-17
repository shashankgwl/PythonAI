param(
    [Parameter(Mandatory = $true)]
    [string]$RibbonDiffPath,

    [Parameter(Mandatory = $true)]
    [string]$TableLogicalName,

    [Parameter(Mandatory = $true)]
    [ValidateSet('mainForm','mainGrid','subGrid','associatedView')]
    [string]$Location,

    [Parameter(Mandatory = $true)]
    [string]$ButtonLabel,

    [Parameter(Mandatory = $false)]
    [string]$PublisherPrefix = 'new',

    [Parameter(Mandatory = $false)]
    [ValidateSet('none','javascript')]
    [string]$ActionType = 'none',

    [Parameter(Mandatory = $false)]
    [string]$WebResourceName,

    [Parameter(Mandatory = $false)]
    [string]$FunctionName,

    [Parameter(Mandatory = $false)]
    [int]$Sequence = 100,

    [Parameter(Mandatory = $false)]
    [string]$ContainerLocation,

    [Parameter(Mandatory = $false)]
    [bool]$AddRefreshDisplayRule = $true,

    [Parameter(Mandatory = $false)]
    [string]$NoOpWebResourceName,

    [Parameter(Mandatory = $false)]
    [string]$NoOpFunctionName = 'RibbonNoop.click'
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
    $existing = $Root.SelectSingleNode($XPath.Replace('{id}', $Id))
    if ($existing -and $existing.ParentNode) {
        [void]$existing.ParentNode.RemoveChild($existing)
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

function Resolve-EntityToken([string]$RibbonPath, [string]$FallbackTableLogicalName) {
    $folder = Split-Path -Parent $RibbonPath
    $entityXmlPath = Join-Path $folder 'Entity.xml'

    if (Test-Path $entityXmlPath) {
        try {
            [xml]$entityXml = Get-Content -Path $entityXmlPath -Raw -Encoding UTF8

            $schemaName = $null
            $entityNode = $entityXml.SelectSingleNode('/Entity/EntityInfo/entity')
            if ($entityNode -and $entityNode.Attributes['Name']) {
                $schemaName = $entityNode.Attributes['Name'].Value
            }

            if (-not [string]::IsNullOrWhiteSpace($schemaName)) {
                $resolved = $schemaName.ToLowerInvariant()
                if ($FallbackTableLogicalName.ToLowerInvariant() -ne $resolved) {
                    Write-Warning "TableLogicalName '$FallbackTableLogicalName' does not match sibling Entity.xml schema-derived token '$resolved'. Using '$resolved' for ribbon container resolution."
                }
                return $resolved
            }
        }
        catch {
            Write-Warning "Unable to read sibling Entity.xml at '$entityXmlPath'. Falling back to TableLogicalName '$FallbackTableLogicalName'. Error: $($_.Exception.Message)"
        }
    }

    return $FallbackTableLogicalName.ToLowerInvariant()
}

function Add-JavaScriptAction([
    System.Xml.XmlDocument]$Document,
    [System.Xml.XmlElement]$ActionsElement,
    [string]$LibraryName,
    [string]$JsFunctionName
) {
    $js = $Document.CreateElement('JavaScriptFunction')

    $libAttr = $Document.CreateAttribute('Library')
    $libAttr.Value = '$webresource:' + $LibraryName
    [void]$js.Attributes.Append($libAttr)

    $fnAttr = $Document.CreateAttribute('FunctionName')
    $fnAttr.Value = $JsFunctionName
    [void]$js.Attributes.Append($fnAttr)

    $crmParam = $Document.CreateElement('CrmParameter')
    $valueAttr = $Document.CreateAttribute('Value')
    $valueAttr.Value = 'PrimaryControl'
    [void]$crmParam.Attributes.Append($valueAttr)
    [void]$js.AppendChild($crmParam)

    [void]$ActionsElement.AppendChild($js)
}

$tableToken = Resolve-EntityToken -RibbonPath $RibbonDiffPath -FallbackTableLogicalName $TableLogicalName

if (-not $ContainerLocation) {
    switch ($Location) {
        'mainForm'       { $ContainerLocation = "Mscrm.Form.$tableToken.MainTab.Actions.Controls._children" }
        'mainGrid'       { $ContainerLocation = "Mscrm.HomepageGrid.$tableToken.MainTab.Management.Controls._children" }
        'subGrid'        { $ContainerLocation = "Mscrm.SubGrid.$tableToken.MainTab.Actions.Controls._children" }
        'associatedView' { $ContainerLocation = "Mscrm.AssociatedMenu.$tableToken.MainTab.Actions.Controls._children" }
        default          { throw "Unsupported location '$Location'." }
    }
}

$effectiveActionType = $ActionType
$effectiveWebResourceName = $WebResourceName
$effectiveFunctionName = $FunctionName

if ($ActionType -eq 'javascript') {
    if ([string]::IsNullOrWhiteSpace($WebResourceName)) { throw 'WebResourceName is required when ActionType=javascript.' }
    if ([string]::IsNullOrWhiteSpace($FunctionName))    { throw 'FunctionName is required when ActionType=javascript.' }
}
elseif ($ActionType -eq 'none') {
    if (-not [string]::IsNullOrWhiteSpace($NoOpWebResourceName)) {
        $effectiveActionType = 'javascript'
        $effectiveWebResourceName = $NoOpWebResourceName
        $effectiveFunctionName = $NoOpFunctionName
        Write-Warning "ActionType 'none' has been upgraded to a deterministic no-op JavaScript binding using web resource '$effectiveWebResourceName' and function '$effectiveFunctionName'. Make sure this web resource exists in the target solution."
    }
    else {
        Write-Warning "ActionType 'none' will produce an empty <Actions /> block. In Unified Interface, placeholder buttons with no action may not surface reliably. To force a deterministic visible no-op command, pass -NoOpWebResourceName and optionally -NoOpFunctionName."
    }
}

$idPrefix = ConvertTo-IdPrefix $PublisherPrefix
$slug = New-Slug $ButtonLabel
$idBase = "$idPrefix.$tableToken.$Location.$slug"
$customActionId = "$idBase.CustomAction"
$commandId = "$idBase.Command"
$buttonId = "$idBase.Button"
$displayRuleId = "$idBase.Refresh.DisplayRule"

$doc = if (Test-Path $RibbonDiffPath) {
    $x = New-Object System.Xml.XmlDocument
    $x.PreserveWhitespace = $true
    $x.Load($RibbonDiffPath)
    $x
} else {
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
$ruleDisplayRules = Get-OrCreateChildElement -Parent $ruleDefinitions -Name 'DisplayRules'
[void](Get-OrCreateChildElement -Parent $ruleDefinitions -Name 'EnableRules')
[void](Get-OrCreateChildElement -Parent $root -Name 'LocLabels')

# Remove previous version of the same generated IDs so the script is idempotent.
Remove-NodeById -Root $root -XPath "./CustomActions/CustomAction[@Id='{id}']" -Id $customActionId
Remove-NodeById -Root $root -XPath "./CommandDefinitions/CommandDefinition[@Id='{id}']" -Id $commandId
if ($AddRefreshDisplayRule) {
    Remove-NodeById -Root $root -XPath "./RuleDefinitions/DisplayRules/DisplayRule[@Id='{id}']" -Id $displayRuleId
}

$customAction = $doc.CreateElement('CustomAction')
foreach ($pair in @{
    'Id' = $customActionId
    'Location' = $ContainerLocation
    'Sequence' = [string]$Sequence
}.GetEnumerator()) {
    $a = $doc.CreateAttribute($pair.Key)
    $a.Value = $pair.Value
    [void]$customAction.Attributes.Append($a)
}

$commandUiDefinition = $doc.CreateElement('CommandUIDefinition')
$button = $doc.CreateElement('Button')
foreach ($pair in @{
    'Id' = $buttonId
    'Command' = $commandId
    'LabelText' = $ButtonLabel
    'ToolTipTitle' = $ButtonLabel
    'ToolTipDescription' = $ButtonLabel
    'Sequence' = [string]$Sequence
    'TemplateAlias' = 'o1'
}.GetEnumerator()) {
    $a = $doc.CreateAttribute($pair.Key)
    $a.Value = $pair.Value
    [void]$button.Attributes.Append($a)
}
[void]$commandUiDefinition.AppendChild($button)
[void]$customAction.AppendChild($commandUiDefinition)
[void]$customActions.AppendChild($customAction)

if ($AddRefreshDisplayRule) {
    $displayRule = $doc.CreateElement('DisplayRule')
    $idAttr = $doc.CreateAttribute('Id')
    $idAttr.Value = $displayRuleId
    [void]$displayRule.Attributes.Append($idAttr)

    $clientTypeRule = $doc.CreateElement('CommandClientTypeRule')
    $typeAttr = $doc.CreateAttribute('Type')
    $typeAttr.Value = 'Refresh'
    [void]$clientTypeRule.Attributes.Append($typeAttr)
    [void]$displayRule.AppendChild($clientTypeRule)

    [void]$ruleDisplayRules.AppendChild($displayRule)
}

$commandDefinition = $doc.CreateElement('CommandDefinition')
$a = $doc.CreateAttribute('Id')
$a.Value = $commandId
[void]$commandDefinition.Attributes.Append($a)

$enableRules = $doc.CreateElement('EnableRules')
$displayRules = $doc.CreateElement('DisplayRules')
$actions = $doc.CreateElement('Actions')

if ($AddRefreshDisplayRule) {
    $displayRuleRef = $doc.CreateElement('DisplayRule')
    $displayRuleRefId = $doc.CreateAttribute('Id')
    $displayRuleRefId.Value = $displayRuleId
    [void]$displayRuleRef.Attributes.Append($displayRuleRefId)
    [void]$displayRules.AppendChild($displayRuleRef)
}

if ($effectiveActionType -eq 'javascript') {
    Add-JavaScriptAction -Document $doc -ActionsElement $actions -LibraryName $effectiveWebResourceName -JsFunctionName $effectiveFunctionName
}

[void]$commandDefinition.AppendChild($enableRules)
[void]$commandDefinition.AppendChild($displayRules)
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

Write-Host 'Patched RibbonDiffXml successfully.'
Write-Host "  File: $RibbonDiffPath"
Write-Host "  Resolved table token: $tableToken"
Write-Host "  CustomAction Location: $ContainerLocation"
Write-Host "  CustomAction Id: $customActionId"
Write-Host "  Button Id: $buttonId"
Write-Host "  Command Id: $commandId"
if ($AddRefreshDisplayRule) {
    Write-Host "  DisplayRule Id: $displayRuleId (CommandClientTypeRule=Refresh)"
}
if ($effectiveActionType -eq 'javascript') {
    Write-Host "  Action binding: $effectiveWebResourceName :: $effectiveFunctionName"
}
else {
    Write-Host '  Action binding: <empty actions>'
}
