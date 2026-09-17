$ErrorActionPreference = 'Stop'

$rancherBin = 'D:\Apps\Rancher Desktop\resources\resources\win32\bin'
if (Test-Path -LiteralPath $rancherBin) {
    $env:Path = "$rancherBin;$env:Path"
}

$images = @(
    [pscustomobject]@{
        Source = 'docker.1ms.run/pgvector/pgvector@sha256:eac621400b7b7ff52493883e41e930e3d104695fea5b68cc0c42370cf7880067'
        Target = 'pgvector/pgvector:0.8.6-pg16-bookworm'
        ExpectedDigest = 'sha256:eac621400b7b7ff52493883e41e930e3d104695fea5b68cc0c42370cf7880067'
    }
    [pscustomobject]@{
        Source = 'docker.m.daocloud.io/casbin/casdoor@sha256:25c8df27f3680fd352c7074c3189e578c4c61092c4ee7e2194068ef669366474'
        Target = 'casbin/casdoor:3.161.1'
        ExpectedDigest = 'sha256:25c8df27f3680fd352c7074c3189e578c4c61092c4ee7e2194068ef669366474'
    }
)

foreach ($image in $images) {
    & docker pull $image.Source
    if ($LASTEXITCODE -ne 0) {
        throw "Image pull failed: $($image.Source)"
    }

    $repoDigests = & docker image inspect --format '{{json .RepoDigests}}' $image.Source
    $digestVerified = $repoDigests -like "*@$($image.ExpectedDigest)*"
    if (-not $digestVerified) {
        throw "Pulled image digest does not match $($image.ExpectedDigest): $($image.Source)"
    }

    & docker tag $image.Source $image.Target
    if ($LASTEXITCODE -ne 0) {
        throw "Image tag failed: $($image.Target)"
    }

    Write-Host "Verified and tagged $($image.Target)"
}
