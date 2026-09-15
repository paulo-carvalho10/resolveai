"""Knowledge base articles for the development seed (Portuguese, Brazilian ERP support)."""

from app.models import ArticleStatus

# (title, category name, tags, status, content)
ARTICLES: list[tuple[str, str | None, list[str], ArticleStatus, str]] = [
    (
        "Rejeição 539: duplicidade de NF-e",
        "Fiscal",
        ["nfe", "fiscal", "539", "duplicidade", "rejeicao"],
        ArticleStatus.PUBLISHED,
        """A rejeição 539 (Duplicidade de NF-e com diferença na chave de acesso) acontece quando a \
SEFAZ já possui uma NF-e autorizada com o mesmo número e série, mas com chave de acesso diferente.

Causas mais comuns:
- A nota foi transmitida, a resposta da SEFAZ não chegou ao ERP e o usuário gerou a nota de novo.
- A numeração da série foi reiniciada ou alterada manualmente.

Como resolver:
1. Consulte a nota pela chave no portal da SEFAZ ou pela tela "Consultar situação" do ERP.
2. Se já existir uma NF-e autorizada com esse número, não emita outra: vincule o XML autorizado \
ao pedido pelo menu Fiscal > NF-e > Importar XML autorizado.
3. Se a nota autorizada estiver errada, cancele-a dentro do prazo e emita uma nova com o próximo número.
4. Verifique em Fiscal > Parâmetros > Séries se a próxima numeração está correta para evitar novas \
duplicidades.""",
    ),
    (
        "Certificado digital vencido impede emissão de notas",
        "Fiscal",
        ["certificado-digital", "nfe", "nfse", "a1"],
        ArticleStatus.PUBLISHED,
        """Quando o certificado digital A1 vence, nenhuma NF-e ou NFS-e é transmitida e o ERP exibe \
"Certificado digital inválido ou expirado".

Como verificar a validade:
1. Acesse Configurações > Certificados digitais.
2. Confira a coluna "Válido até".

Como instalar o certificado renovado:
1. Solicite o arquivo .pfx e a senha à certificadora.
2. Em Configurações > Certificados digitais, clique em "Importar" e selecione o arquivo.
3. Informe a senha e marque o certificado como padrão da empresa.
4. Reinicie o serviço de transmissão fiscal e reenvie as notas pendentes.""",
    ),
    (
        "NFS-e rejeitada pela prefeitura: erro de comunicação",
        "Fiscal",
        ["nfse", "prefeitura", "webservice"],
        ArticleStatus.PUBLISHED,
        """Erros de comunicação na NFS-e costumam ocorrer por instabilidade no webservice da prefeitura \
ou por cadastro incompleto do município.

Passos:
1. Verifique no site da prefeitura se há aviso de indisponibilidade do sistema de notas.
2. Confira em Fiscal > NFS-e > Parâmetros se a inscrição municipal e o código do serviço estão \
preenchidos.
3. Se o webservice estiver fora do ar, as notas ficam na fila e são reenviadas automaticamente a \
cada 30 minutos.
4. Persistindo por mais de 24 horas, emita a nota pelo portal da prefeitura e importe o XML no ERP.""",
    ),
    (
        "VPN desconectando com frequência",
        "Infraestrutura",
        ["vpn", "rede", "acesso-remoto"],
        ArticleStatus.PUBLISHED,
        """Quedas frequentes da VPN geralmente são causadas por instabilidade na internet local, \
cliente VPN desatualizado ou tempo de inatividade configurado muito baixo.

Diagnóstico e solução:
1. Teste a conexão sem VPN em um site de medição de velocidade e verifique perda de pacotes.
2. Atualize o cliente VPN para a versão indicada pela equipe de infraestrutura.
3. Nas configurações do cliente, desative a opção "Desconectar após inatividade".
4. Se toda a equipe for afetada ao mesmo tempo, o problema provavelmente está no firewall: \
abra um chamado crítico para a Infraestrutura TI.""",
    ),
    (
        "ERP fora do ar: tela branca após o login",
        "Infraestrutura",
        ["servidor", "indisponibilidade", "login", "erp"],
        ArticleStatus.PUBLISHED,
        """Se nenhum usuário consegue acessar o ERP ou todos veem uma tela branca após o login, trate \
como incidente crítico.

Primeiras verificações:
1. Confirme se o problema afeta todos os usuários ou apenas uma filial.
2. Verifique a página de status dos servidores em status.acme.local.
3. Reinicie o serviço de aplicação no servidor pelo painel de administração, se tiver permissão.
4. Limpe o cache do navegador e teste em uma janela anônima para descartar problema local.

Se o serviço não voltar em 15 minutos, acione o plantão da Infraestrutura TI pelo telefone de \
emergência e registre o horário de início da indisponibilidade no chamado.""",
    ),
    (
        "Boleto gerado com vencimento ou valor incorreto",
        "Cobrança",
        ["boleto", "cobranca", "vencimento"],
        ArticleStatus.PUBLISHED,
        """Boletos com vencimento ou valor errado normalmente vêm de condição de pagamento incorreta \
no pedido ou de juros configurados na carteira de cobrança.

Como corrigir:
1. Cancele o boleto em Financeiro > Cobrança > Boletos, informando o motivo.
2. Ajuste a condição de pagamento do título em Financeiro > Contas a receber.
3. Gere um novo boleto e envie a segunda via ao cliente pelo botão "Enviar por e-mail".
4. Se o boleto já foi registrado no banco, peça a baixa do registro antigo para evitar cobrança duplicada.""",
    ),
    (
        "Como redefinir a senha de acesso ao ERP",
        "Acesso",
        ["senha", "login", "acesso"],
        ArticleStatus.PUBLISHED,
        """Para redefinir a senha:
1. Na tela de login, clique em "Esqueci minha senha".
2. Informe o e-mail corporativo cadastrado.
3. Abra o link recebido em até 30 minutos e cadastre uma nova senha com pelo menos 10 caracteres.

Se o e-mail não chegar, verifique a caixa de spam. Após 5 tentativas erradas o usuário é \
bloqueado por 15 minutos; se precisar de desbloqueio imediato, peça ao administrador em \
Administração > Usuários > Desbloquear.""",
    ),
    (
        "Rascunho: novo layout do SPED Fiscal 2027",
        "Fiscal",
        ["sped", "rascunho"],
        ArticleStatus.DRAFT,
        """Artigo em elaboração com as mudanças previstas no layout do SPED Fiscal para 2027. \
Não publicar até a confirmação do guia prático oficial.""",
    ),
]
