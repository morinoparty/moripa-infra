# 認証: LINODE_TOKEN 環境変数のみ(tfvars にトークンを書かないこと)
provider "linode" {}

module "gateway" {
  source = "../../modules/linode-gateway"

  admin_ssh_keys      = var.admin_ssh_keys
  bootstrap_ssh_cidrs = var.bootstrap_ssh_cidrs
  public_tcp_ports    = var.public_tcp_ports
}

variable "admin_ssh_keys" {
  description = "管理ユーザーの SSH 公開鍵"
  type        = list(string)
}

variable "bootstrap_ssh_cidrs" {
  description = "SSH を一時許可する CIDR(定常は空)"
  type        = list(string)
  default     = []
}

variable "public_tcp_ports" {
  description = "公開 TCP ポート(ansible の dnat_rules と check-consistency で突合)"
  type        = list(number)
  default     = [80, 443, 25565]
}
