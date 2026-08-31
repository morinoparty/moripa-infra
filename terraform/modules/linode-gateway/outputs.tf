output "public_ip" {
  description = "ゲートウェイのパブリック IP(ansible の gateway_public_ip へ転記)"
  value       = tolist(linode_instance.gateway.ipv4)[0]
}

output "instance_id" {
  value = linode_instance.gateway.id
}

output "admin_username" {
  value = var.admin_username
}
