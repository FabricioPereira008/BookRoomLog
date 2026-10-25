# Changelog

Todas as mudanças relevantes do BookRoomLog ficam registradas aqui.

## [Não lançado]

### Adicionado
- **Preencher automaticamente** no cadastro: busca o livro (ISBN, ou título + autor) e completa só os campos vazios — autor, gênero, série e volume, editora, páginas, idioma, ISBN e capa — com o resultado mais seguro, mostrando o que foi preenchido.
- **Completar dados faltantes** (Configurações → Busca e capas): faz o mesmo, em lote, para os livros já cadastrados, com progresso e botão de parar.
- Gêneros das APIs (em inglês) traduzidos para gêneros em português (no máximo 2, reaproveitando a grafia dos já cadastrados) e série/volume lidos da Open Library e de padrões no título.

### Alterado
- A busca na Open Library acha também edições traduzidas ("Duna" para a obra "Dune") e prefere as edições em português (título, editora, ISBN e capa da edição brasileira).
- "Buscar dados online" passa a preencher gênero e série e, como o preenchimento automático, nunca troca o que já foi digitado.

## [0.1.0] - 2026-10-25

### Adicionado
- Registro de livros com os status **Quero Ler**, **Próximo**, **Lendo** e **Lido**.
- Campos: título, autores (vários, em ordem), série/saga com volume, gênero principal e secundário, editora, nº de páginas, formato (Kindle/E-book, Físico, Audiobook), idioma, ISBN, capa, favorito e anotações/resenha.
- Nota de 0 a 10 (meio ponto) e data de término para livros lidos (a data de hoje vem preenchida); progresso em % enquanto lê.
- **Estante**: lendo agora em destaque e faixas de próximos, quero ler e lidos recentemente.
- **Fila de Próximos** com ordem manual (arrastar ou botões) e atalho "Começar a ler".
- **Releituras** ligadas ao registro original, com nº da leitura, nota e data próprias.
- **Biblioteca** em tabela com busca e filtros por status, gênero e formato.
- **Anuário de leitura**: livros e páginas por ano, média de notas, livros por mês, gêneros, autores e formatos, destaques e pódio (top 3).
- Páginas de **Autores, Gêneros, Séries e Editoras** com mosaico de capas e detalhes.
- **Busca de dados online** (Google Books, com a Open Library como alternativa) por título/autor ou ISBN, preenchendo o formulário e baixando a capa.
- Capas por busca automática, link ou arquivo; limpeza de capas sem uso e busca em lote das que faltam.
- Backups automáticos diários, manuais, restauração e exportação/importação em .zip.
- Busca rápida (Ctrl+F), novo livro (Ctrl+N), excluir selecionado (Del) e tema escuro.
