package fridget.fridget.recipe;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import fridget.fridget.ingredient.IngredientService;
import fridget.fridget.ingredient.UserIngredient;
import fridget.fridget.user.UserService;
import fridget.fridget.user.dto.UserPreferenceDto;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.*;

@Service
public class RecipeService {

    private final IngredientService ingredientService;
    private final UserService userService;
    private final ObjectMapper objectMapper;
    private final RestTemplate restTemplate;

    public RecipeService(IngredientService ingredientService, UserService userService) {
        this.ingredientService = ingredientService;
        this.userService = userService;
        this.objectMapper = new ObjectMapper();
        this.restTemplate = new RestTemplate();
    }

    public List<Recipe> generateRecipes() {
        long totalStart = System.currentTimeMillis();
        try {
            // 1. 사용자 재료 가져오기
            List<UserIngredient> userIngredientsList = ingredientService.findMyIngredients();
            List<String> userIngredients = new ArrayList<>();
            for (UserIngredient ingredient : userIngredientsList) {
                userIngredients.add(ingredient.getName());
            }
            System.out.println("🥬 사용자 재료: " + userIngredients);

            UserPreferenceDto userPreferenceDto = userService.findMyPreferences();
            // 2. Flask 서버로 요청
            String flaskUrl = "http://localhost:5001/generate"; // or 배포된 서버 주소

            Map<String, Object> body = new HashMap<>();
            body.put("userIngredients", userIngredients);
            body.put("userPreferences", userPreferenceDto);
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(body, headers);

            long callStart = System.currentTimeMillis();
            ResponseEntity<String> response = restTemplate.postForEntity(flaskUrl, entity, String.class);
            long callEnd = System.currentTimeMillis();

            if (response.getStatusCode() != HttpStatus.OK) {
                System.out.println("Flask 서버 호출 실패: " + response.getStatusCode());
                return Collections.emptyList();
            }

            // 3. 결과 파싱
            String jsonContent = response.getBody();
            List<Recipe> recipes = objectMapper.readValue(jsonContent, new TypeReference<List<Recipe>>() {
            });

            // 4. 재료 누락 정보 계산
            for (Recipe recipe : recipes) {
                List<String> missingIngredients = new ArrayList<>();
                for (Ingredient ingredient : recipe.getIngredients()) {
                    if (!userIngredients.contains(ingredient.getName().toLowerCase())) {
                        missingIngredients.add(ingredient.getName());
                    }
                }
                recipe.setMissingIngredients(missingIngredients);
            }

            long totalEnd = System.currentTimeMillis();
            System.out.println("Flask 호출 시간: " + (callEnd - callStart) + " ms");
            System.out.println("총 소요 시간: " + (totalEnd - totalStart) + " ms (" + ((totalEnd - totalStart) / 1000.0) + "초)");

            return recipes;

        } catch (Exception e) {
            e.printStackTrace();
            return Collections.emptyList();
        }
    }
}