terraform {
  required_providers {
    linode = {
      source  = "linode/linode"
      version = "~> 3.0"
    }
  }
}

resource "linode_instance" "gateway" {
  label  = var.label
  region = var.region
  type   = var.instance_type
  image  = var.image

  metadata {
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
      admin_username = var.admin_username
      admin_ssh_keys = var.admin_ssh_keys
    }))
  }
}

resource "linode_firewall" "gateway" {
  label = "${var.label}-fw"

  inbound_policy  = "DROP"
  outbound_policy = "ACCEPT"

  inbound {
    label    = "wireguard"
    action   = "ACCEPT"
    protocol = "UDP"
    ports    = tostring(var.wg_port)
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }

  inbound {
    label    = "public-tcp"
    action   = "ACCEPT"
    protocol = "TCP"
    ports    = join(",", var.public_tcp_ports)
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }

  # 初回ブートストラップ時のみ。定常状態では bootstrap_ssh_cidrs = [] で
  # このルールごと消え、SSH は WireGuard 経由のみになる
  dynamic "inbound" {
    for_each = length(var.bootstrap_ssh_cidrs) > 0 ? [1] : []
    content {
      label    = "bootstrap-ssh"
      action   = "ACCEPT"
      protocol = "TCP"
      ports    = "22"
      ipv4     = var.bootstrap_ssh_cidrs
    }
  }

  inbound {
    label    = "icmp"
    action   = "ACCEPT"
    protocol = "ICMP"
    ipv4     = ["0.0.0.0/0"]
    ipv6     = ["::/0"]
  }

  linodes = [linode_instance.gateway.id]
}
