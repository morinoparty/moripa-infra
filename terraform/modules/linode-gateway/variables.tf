variable "label" {
  description = "Linode インスタンスのラベル"
  type        = string
  default     = "moripa-gw"
}

variable "region" {
  description = "リージョン(東京)"
  type        = string
  default     = "ap-northeast"
}

variable "instance_type" {
  description = "インスタンスタイプ(Nanode 1GB)"
  type        = string
  default     = "g6-nanode-1"
}

variable "image" {
  description = "OS イメージ"
  type        = string
  default     = "linode/ubuntu26.04"
}

variable "admin_username" {
  description = "管理ユーザー名(cloud-init で作成)"
  type        = string
  default     = "moripa"
}

variable "admin_ssh_keys" {
  description = "管理ユーザーの SSH 公開鍵"
  type        = list(string)
}

variable "wg_port" {
  description = "WireGuard の listen ポート"
  type        = number
  default     = 51820
}

variable "bootstrap_ssh_cidrs" {
  description = "SSH(22/tcp) を許可する CIDR。初回 Ansible 実行時のみ管理者の現IPを入れ、wg 確立後は空にして再 apply する"
  type        = list(string)
  default     = []
}

variable "public_tcp_ports" {
  description = "外部公開する TCP ポート(nftables の DNAT 対象と一致させること)"
  type        = list(number)
  default     = [80, 443, 25565]
}
