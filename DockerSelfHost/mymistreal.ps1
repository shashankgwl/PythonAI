# Path to your input file
$promptFile = "prompt.txt"
$promptRaw  = Get-Content -Raw -Path $promptFile


# Build the JSON request body safely
$bodyObject = [PSCustomObject]@{
    model  = "mistral"
    prompt = $promptRaw.Replace('\', '\\').Replace('"', '\"')
    stream = $true
}
$body = $bodyObject | ConvertTo-Json -Depth 3 -Compress
$body = $body -replace '"True"', 'true'

#Write-Host "JSON body being sent:`n$body`n"

# Create raw HTTP request
$request = [System.Net.HttpWebRequest]::Create("http://ollamatest2.bza5gzf2hec2eth4.eastus2.azurecontainer.io:11434/api/generate")
$request.Method = "POST"
$request.ContentType = "application/json"
$request.Timeout = 1800000           

# Write JSON body
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$request.ContentLength = $bytes.Length
$reqStream = $request.GetRequestStream()
$reqStream.Write($bytes, 0, $bytes.Length)
$reqStream.Close()

# Get streaming response
$response = $request.GetResponse()
$stream   = $response.GetResponseStream()
$reader   = New-Object System.IO.StreamReader($stream)

$fullResponse = ""

while (-not $reader.EndOfStream) {
    $line = $reader.ReadLine()
    if ([string]::IsNullOrWhiteSpace($line)) { continue }

    try {
        $json = $line | ConvertFrom-Json
        if ($json.response) {
            $fullResponse += $json.response
            Write-Host -NoNewline $json.response
        }
    } catch {
        Write-Host "`nSkipping malformed line: $line"
    }
}

Write-Host "`n`nFinal response from Mistral:`n"
Write-Host $fullResponse
