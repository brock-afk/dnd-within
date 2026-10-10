# Bicep

One module per layer, composed by `main.bicep`, with parameters in `*.bicepparam` files.

    az deployment group what-if  -g <resource group> -f <file>.bicep -p <file>.bicepparam
    az deployment group create   -g <resource group> -f <file>.bicep -p <file>.bicepparam
    az bicep build -f <file>.bicep        # writes <file>.json: the ARM template, to read
