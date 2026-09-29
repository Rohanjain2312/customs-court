# Private ECR repositories for the two ARM64 images. deploy.sh pushes to them.

resource "aws_ecr_repository" "mcp" {
  name                 = "${replace(var.name_prefix, "_", "-")}-mcp"
  image_tag_mutability = "IMMUTABLE"
  # destroy.sh removes the images with the repository.
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_repository" "agent" {
  name                 = "${replace(var.name_prefix, "_", "-")}-agent"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

# Keep storage cost flat: only the 3 newest images per repository survive.
resource "aws_ecr_lifecycle_policy" "keep_recent" {
  for_each   = { mcp = aws_ecr_repository.mcp.name, agent = aws_ecr_repository.agent.name }
  repository = each.value
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire all but the 3 newest images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}
