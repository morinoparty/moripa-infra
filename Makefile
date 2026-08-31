SHELL := /bin/bash
VENV := .venv
TF_DIR := terraform/envs/prod

# ---- セットアップ -----------------------------------------------------------

.PHONY: venv
venv: ## Ansible/lint 用の Python 仮想環境を作成
	uv venv $(VENV)
	uv pip install --python $(VENV)/bin/python ansible-core ansible-lint yamllint

.PHONY: ansible-deps
ansible-deps: ## Ansible collection を導入
	$(VENV)/bin/ansible-galaxy collection install -r ansible/requirements.yml

# ---- Terraform --------------------------------------------------------------

.PHONY: tf-init tf-plan tf-apply tf-output
tf-init:
	terraform -chdir=$(TF_DIR) init

tf-plan:
	terraform -chdir=$(TF_DIR) plan

tf-apply:
	terraform -chdir=$(TF_DIR) apply

tf-output: ## gateway_public_ip を表示(ansible/group_vars/all/network.yml へ転記する)
	@echo "gateway_public_ip: $$(terraform -chdir=$(TF_DIR) output -raw public_ip)"
	@echo "↑ この値を ansible/group_vars/all/network.yml に転記すること"

# ---- Ansible ----------------------------------------------------------------

.PHONY: gateway cluster site
gateway: ## Linode ゲートウェイを構成
	cd ansible && ../$(VENV)/bin/ansible-playbook playbooks/gateway.yml

cluster: ## 6台のノードを構成(wg → k8s)
	cd ansible && ../$(VENV)/bin/ansible-playbook playbooks/cluster.yml

site: ## 全体を構成
	cd ansible && ../$(VENV)/bin/ansible-playbook playbooks/site.yml

# ---- WireGuard 鍵管理 -------------------------------------------------------

.PHONY: wg-keygen
wg-keygen: ## 使い方: make wg-keygen HOST=node1 (wg と sops が必要)
ifndef HOST
	$(error HOST を指定すること: make wg-keygen HOST=node1)
endif
	@umask 077; \
	priv=$$(wg genkey); pub=$$(echo "$$priv" | wg pubkey); \
	mkdir -p ansible/host_vars/$(HOST); \
	printf 'wg_private_key: %s\n' "$$priv" > ansible/host_vars/$(HOST)/wireguard.sops.yml; \
	sops -e -i ansible/host_vars/$(HOST)/wireguard.sops.yml; \
	echo "wg_public_key: $$pub"; \
	echo "↑ 公開鍵を ansible/host_vars/$(HOST)/main.yml に追記すること"

.PHONY: node-bootstrap
node-bootstrap: ## 使い方: make node-bootstrap HOST=site1-node1 (現地作業者に渡す1回きりのスクリプトを生成)
ifndef HOST
	$(error HOST を指定すること: make node-bootstrap HOST=site1-node1)
endif
	$(VENV)/bin/python scripts/gen_node_bootstrap.py $(HOST) > bootstrap-$(HOST).sh
	@echo "生成: bootstrap-$(HOST).sh(wg 秘密鍵を含む。安全な経路で渡し、実行後は削除させること)"

# ---- ArgoCD bootstrap(一度きりの操作)-------------------------------------

.PHONY: bootstrap-argocd
bootstrap-argocd: ## 使い方: make bootstrap-argocd SITE=site1 (KUBECONFIG はその拠点のクラスタを指すこと)
ifndef SITE
	$(error SITE を指定すること: make bootstrap-argocd SITE=site1)
endif
	kubectl apply -k kubernetes/sites/$(SITE)/bootstrap/argocd
	sops -d kubernetes/sites/$(SITE)/bootstrap/secrets/sops-age.sops.yaml | kubectl apply -f -
	sops -d kubernetes/sites/$(SITE)/bootstrap/secrets/repo-moripa-infra.sops.yaml | kubectl apply -f -
	kubectl apply -f kubernetes/sites/$(SITE)/bootstrap/root-app.yaml

# ---- 検証 -------------------------------------------------------------------

.PHONY: lint lint-yaml lint-terraform lint-ansible lint-helm lint-kustomize check-consistency
lint: lint-yaml lint-terraform lint-ansible lint-helm lint-kustomize check-consistency

lint-yaml:
	$(VENV)/bin/yamllint .

lint-terraform:
	terraform fmt -check -recursive terraform/
	terraform -chdir=$(TF_DIR) init -backend=false -input=false > /dev/null
	terraform -chdir=$(TF_DIR) validate

lint-ansible:
	cd ansible && ../$(VENV)/bin/ansible-lint
	cd ansible && for pb in playbooks/*.yml; do \
	  [ -e "$$pb" ] && ../$(VENV)/bin/ansible-playbook --syntax-check "$$pb"; done; true
	cd ansible && ../$(VENV)/bin/ansible-inventory --list > /dev/null

lint-helm: ## Cilium values (common + 各 site) が chart に対して有効か検証
	@ver=$$(grep -oP 'cilium_version: "\K[^"]+' ansible/group_vars/all/versions.yml); \
	for s in site1 site2; do \
	  helm template cilium cilium --repo https://helm.cilium.io \
	    --version $$ver -n kube-system \
	    -f kubernetes/common/cilium/values.yaml \
	    -f kubernetes/sites/$$s/infrastructure/cilium/values.yaml > /dev/null \
	    && echo "cilium values OK ($$s)" || exit 1; \
	done

KUSTOMIZE_DIRS := \
  kubernetes/common/argocd \
  kubernetes/common/gateway-api-crds \
  kubernetes/common/cert-manager \
  kubernetes/sites/site1/bootstrap/argocd \
  kubernetes/sites/site1/bootstrap/applications \
  kubernetes/sites/site1/infrastructure/ingress \
  kubernetes/sites/site1/infrastructure/monitoring \
  kubernetes/sites/site1/apps \
  kubernetes/sites/site1/apps/minecraft \
  kubernetes/sites/site2/bootstrap/argocd \
  kubernetes/sites/site2/bootstrap/applications \
  kubernetes/sites/site2/infrastructure/ingress \
  kubernetes/sites/site2/infrastructure/monitoring \
  kubernetes/sites/site2/apps

lint-kustomize: ## ksops generator(秘密)を含む overlay は対象外(CI と同方針)
	@for d in $(KUSTOMIZE_DIRS); do \
	  echo "== $$d"; kubectl kustomize "$$d" > /dev/null || exit 1; done
	@echo "kustomize OK"

check-consistency: ## group_vars ↔ cilium values ↔ terraform の整合を検査
	$(VENV)/bin/python scripts/check_consistency.py
	scripts/check_secrets.sh

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-20s %s\n", $$1, $$2}'
