terraform {
  required_version = ">= 1.9"

  required_providers {
    linode = {
      source  = "linode/linode"
      version = "~> 3.0"
    }
  }
}
